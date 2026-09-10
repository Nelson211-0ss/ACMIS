"""Finance and administration endpoints."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query, status
from pydantic import Field
from sqlalchemy import select

from acmis.core.abac import authorize
from acmis.core.audit import AuditCategory, emit
from acmis.core.deps import AnyContext, PageQuery, StaffContext, StudentContext
from acmis.core.errors import Conflict, RuleViolation
from acmis.core.models import utcnow
from acmis.core.pagination import keyset_page
from acmis.core.schemas import Page, Reason, Schema
from acmis.modules.finance import latepayment, service
from acmis.modules.finance.models import (
    DunningNotice,
    FeeStructure,
    Invoice,
    LatePaymentRule,
    Payment,
    PaymentPlan,
    PaymentStatus,
    PenaltyCharge,
    Waiver,
)
from acmis.routers._common import get_or_404

router = APIRouter(prefix="/finance", tags=["finance"])


class InvoiceOut(Schema):
    id: uuid.UUID
    number: str
    student_id: uuid.UUID | None
    applicant_id: uuid.UUID | None
    semester_id: uuid.UUID | None
    kind: str
    currency: str
    subtotal_minor: int
    total_minor: int
    paid_minor: int
    waived_minor: int
    balance_minor: int
    sponsor_portion_minor: int
    status: str
    issued_on: date | None
    due_on: date | None


class PaymentOut(Schema):
    id: uuid.UUID
    reference: str
    receipt_number: str | None
    student_id: uuid.UUID | None
    method: str
    provider: str | None
    currency: str
    amount_minor: int
    allocated_minor: int
    status: str
    value_date: date | None
    settled_at: datetime | None
    payer_name: str | None
    payer_narrative: str | None


@router.get("/students/{student_id}/statement", response_model=dict)
def student_statement(student_id: uuid.UUID, ctx: AnyContext) -> dict[str, Any]:
    """A student's full ledger: invoices, receipts and the running balance.

    Recomputed from the ledger on read rather than trusting the cached
    balance, because this is the number a student is asked to act on and it
    must be the one the entries support.
    """
    from acmis.modules.students.models import Student

    student = get_or_404(ctx, Student, student_id)
    authorize(
        engine=ctx.engine,
        action="student_ledger:read_statement",
        resource_type="student_ledger",
        resource={"id": None, "student_id": str(student.id)},
        category=AuditCategory.FINANCE,
        audit_reads=True,
    )
    return service.student_statement(ctx.db, student_id=student_id)


@router.get("/me/statement", response_model=dict)
def my_statement(ctx: StudentContext) -> dict[str, Any]:
    authorize(
        engine=ctx.engine,
        action="student_ledger:read_statement",
        resource_type="student_ledger",
        resource={"id": None, "student_id": str(ctx.student_id)},
        category=AuditCategory.FINANCE,
    )
    return service.student_statement(ctx.db, student_id=ctx.student_id)


@router.get("/invoices", response_model=Page[InvoiceOut])
def list_invoices(
    ctx: StaffContext,
    page: PageQuery,
    student_id: uuid.UUID | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    overdue_only: bool = False,
) -> Page[InvoiceOut]:
    authorize(
        engine=ctx.engine,
        action="invoice:list",
        resource_type="invoice",
        resource={"id": None, "status": status_filter},
        category=AuditCategory.FINANCE,
    )
    stmt = select(Invoice).where(Invoice.deleted_at.is_(None))
    if student_id:
        stmt = stmt.where(Invoice.student_id == student_id)
    if status_filter:
        stmt = stmt.where(Invoice.status == status_filter)
    if overdue_only:
        stmt = stmt.where(Invoice.due_on < date.today(), Invoice.balance_minor > 0)
    found = keyset_page(
        ctx.db,
        stmt,
        page=page,
        key=Invoice.issued_on,
        ident=Invoice.id,
        descending=True,
        nulls="last",
    )
    return Page.of(
        [InvoiceOut.model_validate(r) for r in found.rows],
        limit=page.limit,
        next_cursor=found.next_cursor,
        total=found.total,
    )


class SemesterInvoiceIn(Schema):
    student_id: uuid.UUID
    semester_id: uuid.UUID


@router.post("/invoices/semester", response_model=InvoiceOut, status_code=status.HTTP_201_CREATED)
def raise_semester_invoice(payload: SemesterInvoiceIn, ctx: StaffContext) -> InvoiceOut:
    from acmis.modules.students.models import Student, StudentProgramme

    student = get_or_404(ctx, Student, payload.student_id)
    authorize(
        engine=ctx.engine,
        action="invoice:create",
        resource_type="invoice",
        resource={"id": None, "student_id": str(student.id), "status": "draft"},
        category=AuditCategory.FINANCE,
    )
    programme = ctx.db.execute(
        select(StudentProgramme).where(
            StudentProgramme.student_id == student.id,
            StudentProgramme.is_primary.is_(True),
            StudentProgramme.deleted_at.is_(None),
        )
    ).scalar_one()
    invoice = service.raise_semester_invoice(
        ctx.db,
        student=student,
        student_programme=programme,
        semester_id=payload.semester_id,
        actor_id=ctx.principal.id,
    )
    return InvoiceOut.model_validate(invoice)


class RecordPaymentIn(Schema):
    student_id: uuid.UUID | None = None
    applicant_id: uuid.UUID | None = None
    amount_minor: Annotated[int, Field(gt=0)]
    currency: str = "UGX"
    method: str
    provider: str | None = None
    provider_reference: str | None = None
    payer_name: str | None = None
    payer_narrative: str | None = None
    value_date: date | None = None


@router.post("/payments", response_model=PaymentOut, status_code=status.HTTP_201_CREATED)
def record_payment(payload: RecordPaymentIn, ctx: StaffContext) -> PaymentOut:
    """Receipt a payment at the counter or from a provider callback.

    A payment with no identifiable owner is accepted as `unmatched` rather
    than refused. Money that arrived did arrive; recording it as a failure is
    how a deposit with a mistyped student number is never resolved.
    """
    authorize(
        engine=ctx.engine,
        action="payment:record",
        resource_type="payment",
        resource={
            "id": None,
            "student_id": str(payload.student_id) if payload.student_id else None,
            "status": "pending",
            "amount_minor": payload.amount_minor,
        },
        category=AuditCategory.FINANCE,
    )
    payment = service.record_payment(
        ctx.db,
        student_id=payload.student_id,
        applicant_id=payload.applicant_id,
        amount_minor=payload.amount_minor,
        currency=payload.currency,
        method=payload.method,
        provider=payload.provider,
        provider_reference=payload.provider_reference,
        payer_narrative=payload.payer_narrative,
        payer_name=payload.payer_name,
        value_date=payload.value_date,
        actor_id=ctx.principal.id,
    )
    return PaymentOut.model_validate(payment)


@router.get("/payments/unmatched", response_model=Page[PaymentOut])
def list_unmatched(ctx: StaffContext, page: PageQuery) -> Page[PaymentOut]:
    """The bursary's work queue: money in, owner unknown."""
    authorize(
        engine=ctx.engine,
        action="payment:list",
        resource_type="payment",
        resource={"id": None, "status": "unmatched"},
        category=AuditCategory.FINANCE,
    )
    found = keyset_page(
        ctx.db,
        select(Payment).where(
            Payment.status == PaymentStatus.UNMATCHED, Payment.deleted_at.is_(None)
        ),
        page=page,
        key=Payment.value_date,
        ident=Payment.id,
        # Oldest first, and money with no value date first of all: the longer a
        # receipt sits unmatched the more likely the student has already been
        # sent a reminder for a fee they paid.
        nulls="first",
    )
    return Page.of(
        [PaymentOut.model_validate(r) for r in found.rows],
        limit=page.limit,
        next_cursor=found.next_cursor,
        total=found.total,
    )


class MatchPaymentIn(Schema):
    student_id: uuid.UUID


@router.post("/payments/{payment_id}/match", response_model=PaymentOut)
def match_payment(payment_id: uuid.UUID, payload: MatchPaymentIn, ctx: StaffContext) -> PaymentOut:
    payment = get_or_404(ctx, Payment, payment_id)
    authorize(
        engine=ctx.engine,
        action="payment:allocate",
        resource_type="payment",
        resource=payment,
        category=AuditCategory.FINANCE,
    )
    return PaymentOut.model_validate(
        service.match_unmatched_payment(
            ctx.db, payment=payment, student_id=payload.student_id, actor_id=ctx.principal.id
        )
    )


@router.post("/payments/{payment_id}/reverse", response_model=PaymentOut)
def reverse_payment(payment_id: uuid.UUID, payload: Reason, ctx: StaffContext) -> PaymentOut:
    payment = get_or_404(ctx, Payment, payment_id)
    authorize(
        engine=ctx.engine,
        action="payment:reverse",
        resource_type="payment",
        resource=payment,
        category=AuditCategory.FINANCE,
    )
    return PaymentOut.model_validate(
        service.reverse_payment(
            ctx.db, payment=payment, actor_id=ctx.principal.id, reason=payload.reason
        )
    )


class WaiverIn(Schema):
    student_id: uuid.UUID
    invoice_id: uuid.UUID | None = None
    category: str
    amount_minor: Annotated[int, Field(gt=0)]
    reason: Annotated[str, Field(min_length=10, max_length=2000)]
    evidence_reference: str | None = None


class WaiverOut(Schema):
    id: uuid.UUID
    reference: str
    student_id: uuid.UUID
    invoice_id: uuid.UUID | None
    category: str
    amount_minor: int
    currency: str
    reason: str
    status: str
    raised_by_id: uuid.UUID
    raised_at: datetime
    released_by_id: uuid.UUID | None
    released_at: datetime | None


@router.post("/waivers", response_model=WaiverOut, status_code=status.HTTP_201_CREATED)
def raise_waiver(payload: WaiverIn, ctx: StaffContext) -> WaiverOut:
    authorize(
        engine=ctx.engine,
        action="waiver:create",
        resource_type="waiver",
        resource={
            "id": None,
            "student_id": str(payload.student_id),
            "status": "raised",
            "amount_minor": payload.amount_minor,
            "category": payload.category,
        },
        category=AuditCategory.FINANCE,
    )
    return WaiverOut.model_validate(
        service.raise_waiver(
            ctx.db,
            student_id=payload.student_id,
            invoice_id=payload.invoice_id,
            category=payload.category,
            amount_minor=payload.amount_minor,
            reason=payload.reason,
            evidence_reference=payload.evidence_reference,
            actor_id=ctx.principal.id,
        )
    )


@router.post("/waivers/{waiver_id}/release", response_model=WaiverOut)
def release_waiver(waiver_id: uuid.UUID, payload: Reason, ctx: StaffContext) -> WaiverOut:
    """Release a waiver. Requires a different person and a spending ceiling.

    `finance.four-eyes` refuses the raiser, and `waiver-ceiling` refuses an
    amount above the releaser's limit — the amount is on the resource, and the
    ceiling is an attribute of the principal derived from their permissions.
    """
    waiver = get_or_404(ctx, Waiver, waiver_id)
    authorize(
        engine=ctx.engine,
        action="waiver:release",
        resource_type="waiver",
        resource=waiver,
        category=AuditCategory.FINANCE,
    )
    return WaiverOut.model_validate(
        service.release_waiver(
            ctx.db, waiver=waiver, actor_id=ctx.principal.id, note=payload.reason
        )
    )


class FeeStructureOut(Schema):
    id: uuid.UUID
    code: str
    name: str
    academic_year_id: uuid.UUID
    programme_id: uuid.UUID | None
    sponsorship: str | None
    currency: str
    status: str
    registration_threshold_percent: int
    exam_threshold_percent: int


@router.get("/fee-structures", response_model=Page[FeeStructureOut])
def list_fee_structures(
    ctx: AnyContext,
    page: PageQuery,
    academic_year_id: uuid.UUID | None = None,
    programme_id: uuid.UUID | None = None,
) -> Page[FeeStructureOut]:
    authorize(
        engine=ctx.engine,
        action="fee_structure:list",
        resource_type="fee_structure",
        resource={"id": None, "status": "published"},
    )
    stmt = select(FeeStructure).where(FeeStructure.deleted_at.is_(None))
    if academic_year_id:
        stmt = stmt.where(FeeStructure.academic_year_id == academic_year_id)
    if programme_id:
        stmt = stmt.where(FeeStructure.programme_id == programme_id)
    found = keyset_page(ctx.db, stmt, page=page, key=FeeStructure.code, ident=FeeStructure.id)
    return Page.of(
        [FeeStructureOut.model_validate(r) for r in found.rows],
        limit=page.limit,
        next_cursor=found.next_cursor,
        total=found.total,
    )


@router.get("/trial-balance/{period_code}", response_model=dict)
def trial_balance(period_code: str, ctx: StaffContext) -> dict[str, Any]:
    """Sum the ledger by account, and say whether it balances.

    `balanced: false` means a transaction was written with legs that do not
    sum to zero, which `post_transaction` is supposed to make impossible. It is
    surfaced rather than tidied away because it would be a genuine bug in the
    one place the system cannot afford one.
    """
    authorize(
        engine=ctx.engine,
        action="journal_entry:read",
        resource_type="journal_entry",
        resource={"id": None, "period_code": period_code},
        category=AuditCategory.FINANCE,
        audit_reads=True,
    )
    return service.trial_balance(ctx.db, period_code=period_code)


# ---------------------------------------------------------------------------
# Late payment: terms, surcharges, plans and reminders
# ---------------------------------------------------------------------------


class LateRuleOut(Schema):
    id: uuid.UUID
    code: str
    name: str
    academic_year_id: uuid.UUID
    programme_id: uuid.UUID | None
    sponsorship: str | None
    grace_days: int
    charge_basis: str
    charge_percent: float | None
    charge_flat_minor: int | None
    recurrence: str
    max_charges: int | None
    charge_cap_minor: int | None
    blocks_registration_after_days: int | None
    blocks_exam_card_after_days: int | None
    blocks_results_after_days: int | None
    is_waivable: bool
    status: str


class LateRuleIn(Schema):
    code: Annotated[str, Field(max_length=40)]
    name: Annotated[str, Field(max_length=200)]
    academic_year_id: uuid.UUID
    programme_id: uuid.UUID | None = None
    sponsorship: Annotated[str | None, Field(max_length=30)] = None
    applies_to_invoice_kind: Annotated[str, Field(max_length=30)] = "semester_fees"
    grace_days: Annotated[int, Field(ge=0, le=180)] = 7
    charge_basis: Annotated[str, Field(pattern="^(percentage|flat)$")] = "percentage"
    charge_percent: Annotated[float | None, Field(ge=0, le=100)] = None
    charge_flat_minor: Annotated[int | None, Field(ge=0)] = None
    recurrence: Annotated[str, Field(pattern="^(once|weekly|monthly|per_semester)$")] = "once"
    max_charges: Annotated[int | None, Field(ge=1, le=52)] = None
    charge_cap_minor: Annotated[int | None, Field(ge=0)] = None
    blocks_registration_after_days: Annotated[int | None, Field(ge=0, le=365)] = None
    blocks_exam_card_after_days: Annotated[int | None, Field(ge=0, le=365)] = None
    blocks_results_after_days: Annotated[int | None, Field(ge=0, le=365)] = None
    is_waivable: bool = True
    charge_fee_item_code: Annotated[str | None, Field(max_length=40)] = None
    effective_from: date | None = None
    effective_to: date | None = None


@router.get("/late-payment-rules", response_model=list[LateRuleOut])
def list_late_payment_rules(
    ctx: AnyContext, academic_year_id: uuid.UUID | None = None
) -> list[LateRuleOut]:
    """The institution's published late-payment terms.

    Readable by students: a surcharge nobody was told about is one that gets
    waived on appeal.
    """
    authorize(
        engine=ctx.engine,
        action="late_payment_rule:list",
        resource_type="late_payment_rule",
        resource={
            "id": None,
            "status": "approved",
            "academic_year_id": None,
            "programme_id": None,
            "is_waivable": True,
        },
        category=AuditCategory.FINANCE,
    )
    stmt = select(LatePaymentRule).where(LatePaymentRule.deleted_at.is_(None))
    if academic_year_id:
        stmt = stmt.where(LatePaymentRule.academic_year_id == academic_year_id)
    if ctx.principal.kind in ("student", "applicant"):
        stmt = stmt.where(LatePaymentRule.status == "approved")
    rows = ctx.db.execute(stmt.order_by(LatePaymentRule.code)).scalars().all()
    return [LateRuleOut.model_validate(row) for row in rows]


@router.post("/late-payment-rules", response_model=LateRuleOut, status_code=status.HTTP_201_CREATED)
def create_late_payment_rule(payload: LateRuleIn, ctx: StaffContext) -> LateRuleOut:
    authorize(
        engine=ctx.engine,
        action="late_payment_rule:create",
        resource_type="late_payment_rule",
        resource={
            "id": None,
            "status": "draft",
            "academic_year_id": str(payload.academic_year_id),
            "programme_id": str(payload.programme_id) if payload.programme_id else None,
            "is_waivable": payload.is_waivable,
        },
        category=AuditCategory.FINANCE,
    )
    if payload.charge_basis == "percentage" and payload.charge_percent is None:
        raise RuleViolation("A percentage rule needs a percentage.", rule="charge_percent_required")
    if payload.charge_basis == "flat" and payload.charge_flat_minor is None:
        raise RuleViolation("A flat rule needs an amount.", rule="charge_amount_required")
    if payload.recurrence != "once" and payload.charge_cap_minor is None:
        raise RuleViolation(
            "A recurring surcharge needs a cap. Without one it compounds into a "
            "debt nobody collects.",
            rule="recurring_needs_cap",
        )
    rule = LatePaymentRule(status="draft", created_by_id=ctx.principal.id, **payload.model_dump())
    ctx.db.add(rule)
    ctx.db.flush()
    emit(
        "late_payment_rule:create",
        AuditCategory.FINANCE,
        resource_type="late_payment_rule",
        resource_id=rule.id,
        resource_label=rule.code,
        summary=f"Late-payment terms drafted: {rule.name}",
    )
    return LateRuleOut.model_validate(rule)


@router.post("/late-payment-rules/{rule_id}/approve", response_model=LateRuleOut)
def approve_late_payment_rule(rule_id: uuid.UUID, ctx: StaffContext) -> LateRuleOut:
    rule = get_or_404(ctx, LatePaymentRule, rule_id)
    authorize(
        engine=ctx.engine,
        action="late_payment_rule:approve",
        resource_type="late_payment_rule",
        resource=rule,
        category=AuditCategory.FINANCE,
    )
    if rule.status == "approved":
        raise Conflict("These terms are already approved.")
    rule.status = "approved"
    rule.approved_by_id = ctx.principal.id
    rule.approved_at = utcnow()
    ctx.db.flush()
    emit(
        "late_payment_rule:approve",
        AuditCategory.FINANCE,
        resource_type="late_payment_rule",
        resource_id=rule.id,
        resource_label=rule.code,
        summary="Late-payment terms approved",
        severity="notice",
    )
    return LateRuleOut.model_validate(rule)


class PenaltyOut(Schema):
    id: uuid.UUID
    student_id: uuid.UUID
    invoice_id: uuid.UUID
    charged_on: date
    days_overdue: int
    balance_at_charge_minor: int
    percent_applied: float | None
    amount_minor: int
    sequence: int
    status: str
    applied_automatically: bool
    reversal_reason: str | None


@router.get("/penalties", response_model=Page[PenaltyOut])
def list_penalties(
    ctx: AnyContext, page: PageQuery, student_id: uuid.UUID | None = None
) -> Page[PenaltyOut]:
    """Surcharges applied, with the arithmetic that produced them."""
    subject = student_id or ctx.principal.student_id
    authorize(
        engine=ctx.engine,
        action="penalty_charge:list",
        resource_type="penalty_charge",
        resource={
            "id": None,
            "student_id": str(subject) if subject else None,
            "invoice_id": None,
            "status": "applied",
            "amount_minor": 0,
            "applied_by_id": None,
        },
        category=AuditCategory.FINANCE,
    )
    stmt = select(PenaltyCharge).where(PenaltyCharge.deleted_at.is_(None))
    if subject is not None:
        stmt = stmt.where(PenaltyCharge.student_id == subject)
    found = keyset_page(
        ctx.db,
        stmt,
        page=page,
        key=PenaltyCharge.charged_on,
        ident=PenaltyCharge.id,
        descending=True,
    )
    return Page.of(
        [PenaltyOut.model_validate(row) for row in found.rows],
        limit=page.limit,
        next_cursor=found.next_cursor,
        total=found.total,
    )


@router.post("/penalties/{charge_id}/reverse", response_model=PenaltyOut)
def reverse_penalty(charge_id: uuid.UUID, payload: Reason, ctx: StaffContext) -> PenaltyOut:
    """Take a surcharge off.

    Most often because a payment had not been posted when the job ran — the
    student paid on time and the bank was slow, and they should not carry the
    cost of the float.
    """
    charge = get_or_404(ctx, PenaltyCharge, charge_id)
    authorize(
        engine=ctx.engine,
        action="penalty_charge:reverse",
        resource_type="penalty_charge",
        resource=charge,
        category=AuditCategory.FINANCE,
    )
    return PenaltyOut.model_validate(
        latepayment.reverse_surcharge(
            ctx.db, charge=charge, reason=payload.reason, actor_id=ctx.principal.id
        )
    )


class InstalmentOut(Schema):
    id: uuid.UUID
    sequence: int
    due_on: date
    amount_minor: int
    paid_minor: int
    status: str
    settled_on: date | None


class PlanOut(Schema):
    id: uuid.UUID
    reference: str
    student_id: uuid.UUID
    invoice_id: uuid.UUID | None
    total_minor: int
    deposit_minor: int
    instalment_count: int
    status: str
    reason: str | None
    requested_at: datetime
    approved_at: datetime | None
    missed_count: int
    instalments: list[InstalmentOut]


class PlanIn(Schema):
    invoice_id: uuid.UUID
    instalments: Annotated[int, Field(ge=1, le=12)] = 3
    student_id: uuid.UUID | None = None
    reason: Annotated[str | None, Field(max_length=2000)] = None
    first_due_on: date | None = None
    deposit_minor: Annotated[int, Field(ge=0)] = 0
    interval_days: Annotated[int, Field(ge=7, le=120)] = 30


@router.post("/payment-plans", response_model=PlanOut, status_code=status.HTTP_201_CREATED)
def request_payment_plan(payload: PlanIn, ctx: AnyContext) -> PlanOut:
    """Propose paying in instalments.

    The schedule is laid out now, before approval, because the schedule is
    what the bursary is being asked to agree to — "can I pay in three" is not
    a proposal anyone can accept or refuse.
    """
    invoice = get_or_404(ctx, Invoice, payload.invoice_id)
    student_id = payload.student_id or invoice.student_id or ctx.principal.student_id
    if student_id is None:
        raise RuleViolation("Say which student this plan is for.", rule="student_required")
    authorize(
        engine=ctx.engine,
        action="payment_plan:create",
        resource_type="payment_plan",
        resource={
            "id": None,
            "student_id": str(student_id),
            "invoice_id": str(invoice.id),
            "status": "requested",
            "total_minor": invoice.balance_minor,
            "requested_by_id": str(ctx.principal.id),
        },
        category=AuditCategory.FINANCE,
    )
    return PlanOut.model_validate(
        latepayment.request_plan(
            ctx.db,
            student_id=student_id,
            invoice=invoice,
            instalments=payload.instalments,
            actor_id=ctx.principal.id,
            reason=payload.reason,
            first_due_on=payload.first_due_on,
            deposit_minor=payload.deposit_minor,
            interval_days=payload.interval_days,
        )
    )


@router.get("/payment-plans", response_model=Page[PlanOut])
def list_payment_plans(
    ctx: AnyContext,
    page: PageQuery,
    student_id: uuid.UUID | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
) -> Page[PlanOut]:
    subject = student_id or ctx.principal.student_id
    authorize(
        engine=ctx.engine,
        action="payment_plan:list",
        resource_type="payment_plan",
        resource={
            "id": None,
            "student_id": str(subject) if subject else None,
            "invoice_id": None,
            "status": status_filter,
            "total_minor": 0,
            "requested_by_id": None,
        },
        category=AuditCategory.FINANCE,
    )
    stmt = select(PaymentPlan).where(PaymentPlan.deleted_at.is_(None))
    if subject is not None:
        stmt = stmt.where(PaymentPlan.student_id == subject)
    if status_filter:
        stmt = stmt.where(PaymentPlan.status == status_filter)
    found = keyset_page(
        ctx.db,
        stmt,
        page=page,
        key=PaymentPlan.requested_at,
        ident=PaymentPlan.id,
        descending=True,
    )
    return Page.of(
        [PlanOut.model_validate(row) for row in found.rows],
        limit=page.limit,
        next_cursor=found.next_cursor,
        total=found.total,
    )


class ApprovePlanIn(Reason):
    #: How many instalments may be missed before the plan defaults. Zero
    #: means the first miss ends it.
    missed_allowance: Annotated[int, Field(ge=0, le=3)] = 0


@router.post("/payment-plans/{plan_id}/approve", response_model=PlanOut)
def approve_payment_plan(plan_id: uuid.UUID, payload: ApprovePlanIn, ctx: StaffContext) -> PlanOut:
    """Agree a plan.

    From here the schedule, not the invoice due date, decides whether the
    student is late — so no surcharge and no block applies while they keep to
    it.
    """
    plan = get_or_404(ctx, PaymentPlan, plan_id)
    authorize(
        engine=ctx.engine,
        action="payment_plan:approve",
        resource_type="payment_plan",
        resource=plan,
        category=AuditCategory.FINANCE,
    )
    return PlanOut.model_validate(
        latepayment.approve_plan(
            ctx.db,
            plan=plan,
            actor_id=ctx.principal.id,
            reason=payload.reason,
            missed_allowance=payload.missed_allowance,
        )
    )


class DunningOut(Schema):
    id: uuid.UUID
    student_id: uuid.UUID
    invoice_id: uuid.UUID | None
    level: int
    channel: str
    sent_on: date
    balance_minor: int
    days_overdue: int
    consequence_stated: str | None
    sent_to_sponsor: bool


@router.get("/reminders", response_model=Page[DunningOut])
def list_reminders(
    ctx: AnyContext, page: PageQuery, student_id: uuid.UUID | None = None
) -> Page[DunningOut]:
    """What the student was actually sent, and when.

    Answers "nobody told me" from the record rather than from memory.
    """
    subject = student_id or ctx.principal.student_id
    authorize(
        engine=ctx.engine,
        action="dunning_notice:list",
        resource_type="dunning_notice",
        resource={
            "id": None,
            "student_id": str(subject) if subject else None,
            "invoice_id": None,
            "level": 1,
        },
        category=AuditCategory.FINANCE,
    )
    stmt = select(DunningNotice).where(DunningNotice.deleted_at.is_(None))
    if subject is not None:
        stmt = stmt.where(DunningNotice.student_id == subject)
    found = keyset_page(
        ctx.db,
        stmt,
        page=page,
        key=DunningNotice.sent_on,
        ident=DunningNotice.id,
        descending=True,
    )
    return Page.of(
        [DunningOut.model_validate(row) for row in found.rows],
        limit=page.limit,
        next_cursor=found.next_cursor,
        total=found.total,
    )


@router.get("/blocks/{student_id}", response_model=dict)
def block_state(student_id: uuid.UUID, ctx: AnyContext) -> dict[str, Any]:
    """What is blocked for this student, under which rule, and what lifts it.

    Shaped for the counter: not "blocked" but which gate and what clears it.
    """
    authorize(
        engine=ctx.engine,
        action="student_ledger:read_statement",
        resource_type="student_ledger",
        resource={"id": None, "student_id": str(student_id)},
        category=AuditCategory.FINANCE,
    )
    return latepayment.block_state(ctx.db, student_id=student_id)


class LateRunIn(Schema):
    #: A dry run reports what *would* be charged and writes nothing. The
    #: bursary looks at this before letting the job loose on a cohort.
    dry_run: bool = True


@router.post("/jobs/late-payment", response_model=dict)
def run_late_payment(ctx: StaffContext, payload: LateRunIn | None = None) -> dict[str, Any]:
    """The nightly late-payment run: surcharges, plan review, reminders."""
    authorize(
        engine=ctx.engine,
        action="penalty_charge:apply",
        resource_type="penalty_charge",
        resource={
            "id": None,
            "student_id": None,
            "invoice_id": None,
            "status": "applied",
            "amount_minor": 0,
            "applied_by_id": str(ctx.principal.id),
        },
        category=AuditCategory.FINANCE,
    )
    body = payload or LateRunIn()
    plans = latepayment.review_plans(ctx.db)
    charges = latepayment.apply_surcharges(ctx.db, actor_id=ctx.principal.id, dry_run=body.dry_run)
    reminders = (
        {"sent": 0, "notices": []}
        if body.dry_run
        else latepayment.send_reminders(ctx.db, actor_id=ctx.principal.id)
    )
    return {"plans": plans, "surcharges": charges, "reminders": reminders}
