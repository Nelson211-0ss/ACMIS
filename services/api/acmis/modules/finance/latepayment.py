"""Late payment: surcharges, instalment plans and reminders.

The position this module implements, and the reason each half exists:

* A **surcharge** without a block collects less, because a student who cannot
  pay is not moved by owing slightly more.
* A **block** without a surcharge collects nothing and loses the student,
  because the only lever left is one the institution does not want to pull.
* Neither, applied to a student who has *agreed a plan and is keeping to it*,
  destroys the plan — so the plan is the authority, and every check here
  consults it before anything else.

Everything is bounded and overridable by a named person for a stated reason.
Hardship is real, and a system with no override gets one anyway: informally,
at the counter, unrecorded.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import structlog
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from acmis.core.audit import AuditCategory, emit
from acmis.core.errors import Conflict, RuleViolation
from acmis.core.models import utcnow
from acmis.modules.finance.models import (
    DunningNotice,
    Invoice,
    InvoiceLine,
    LatePaymentRule,
    PaymentPlan,
    PaymentPlanInstalment,
    PenaltyCharge,
)
from acmis.modules.finance.service import (
    ACCOUNT_FEE_INCOME,
    ACCOUNT_STUDENT_RECEIVABLE,
    post_transaction,
    recompute_balance,
)

log = structlog.get_logger(__name__)

#: The escalation ladder. Each level is a number of days past due, and the
#: wording matters as much as the timing: a student who has been told twice
#: what will happen and then has it happen has been treated fairly.
DUNNING_LADDER: tuple[tuple[int, int, str], ...] = (
    (1, 7, "A reminder. Nothing happens yet."),
    (2, 21, "A surcharge may be applied and registration may be blocked."),
    (3, 42, "Registration and examination clearance are blocked from today."),
    (4, 70, "Referred to the bursary for recovery; results may be withheld."),
)


# ---------------------------------------------------------------------------
# Plans
# ---------------------------------------------------------------------------


def under_active_plan(session: Session, *, invoice_id: uuid.UUID) -> PaymentPlan | None:
    """The plan protecting this invoice, if the student is keeping to it.

    A defaulted plan protects nothing, which is the whole point of recording
    the default: an agreement the student stopped keeping is not an agreement.
    """
    plan = (
        session.execute(
            select(PaymentPlan).where(
                PaymentPlan.invoice_id == invoice_id,
                PaymentPlan.status == "active",
                PaymentPlan.deleted_at.is_(None),
            )
        )
        .scalars()
        .first()
    )
    return plan


def request_plan(
    session: Session,
    *,
    student_id: uuid.UUID,
    invoice: Invoice,
    instalments: int,
    actor_id: uuid.UUID | None,
    reason: str | None = None,
    first_due_on: date | None = None,
    deposit_minor: int = 0,
    interval_days: int = 30,
) -> PaymentPlan:
    """Propose a schedule. Not yet an agreement.

    The instalments are laid out now, before approval, because the thing the
    bursary is being asked to agree to is the *schedule* — "can I pay in
    three" is not a proposal anyone can accept or refuse.
    """
    if instalments < 1:
        raise RuleViolation("A plan needs at least one instalment.", rule="plan_instalments")
    outstanding = invoice.balance_minor
    if outstanding <= 0:
        raise Conflict("This invoice has nothing outstanding.")

    existing = (
        session.execute(
            select(PaymentPlan).where(
                PaymentPlan.invoice_id == invoice.id,
                PaymentPlan.status.in_(("requested", "active")),
                PaymentPlan.deleted_at.is_(None),
            )
        )
        .scalars()
        .first()
    )
    if existing is not None:
        raise Conflict(f"There is already a {existing.status} plan for this invoice.")

    sequence = (
        int(
            session.execute(
                select(func.count()).where(PaymentPlan.deleted_at.is_(None))
            ).scalar_one()
        )
        + 1
    )
    plan = PaymentPlan(
        reference=f"PLAN/{date.today().year}/{sequence:04d}",
        student_id=student_id,
        invoice_id=invoice.id,
        semester_id=invoice.semester_id,
        total_minor=outstanding,
        deposit_minor=deposit_minor,
        instalment_count=instalments,
        status="requested",
        reason=reason,
        requested_at=utcnow(),
        created_by_id=actor_id,
    )
    session.add(plan)
    session.flush()

    # The remainder after any deposit, split evenly with the rounding
    # remainder on the *first* instalment. On the last, a plan of three on
    # 100,001 would end with an odd final payment nobody expects; on the
    # first, the student pays the extra unit while they are still engaged.
    payable = outstanding - deposit_minor
    base = payable // instalments
    remainder = payable - base * instalments
    start = first_due_on or (date.today() + timedelta(days=interval_days))
    for index in range(1, instalments + 1):
        amount = base + (remainder if index == 1 else 0)
        session.add(
            PaymentPlanInstalment(
                plan_id=plan.id,
                sequence=index,
                due_on=start + timedelta(days=interval_days * (index - 1)),
                amount_minor=amount,
                status="pending",
                created_by_id=actor_id,
            )
        )
    session.flush()
    emit(
        "payment_plan:create",
        AuditCategory.FINANCE,
        resource_type="payment_plan",
        resource_id=plan.id,
        resource_label=plan.reference,
        summary=(
            f"Plan requested: {instalments} instalment(s) on {outstanding / 100:,.0f}"
            + (f" after a deposit of {deposit_minor / 100:,.0f}" if deposit_minor else "")
        ),
    )
    return plan


def approve_plan(
    session: Session,
    *,
    plan: PaymentPlan,
    actor_id: uuid.UUID | None,
    reason: str | None = None,
    missed_allowance: int = 0,
) -> PaymentPlan:
    """Agree a plan. From here the schedule, not the invoice, decides lateness."""
    if plan.status != "requested":
        raise Conflict(f"This plan is {plan.status}.")
    plan.status = "active"
    plan.approved_by_id = actor_id
    plan.approved_at = utcnow()
    plan.missed_allowance = missed_allowance
    if reason:
        plan.reason = reason
    session.flush()
    emit(
        "payment_plan:approve",
        AuditCategory.FINANCE,
        resource_type="payment_plan",
        resource_id=plan.id,
        resource_label=plan.reference,
        summary=(
            f"Plan agreed; {plan.instalment_count} instalment(s). Surcharges and "
            "blocks are suspended while it is kept."
        ),
        severity="notice",
    )
    return plan


def record_plan_payment(
    session: Session, *, plan: PaymentPlan, amount_minor: int, payment_id: uuid.UUID | None
) -> dict[str, Any]:
    """Apply money to the earliest unpaid instalment, then the next.

    Oldest-first rather than letting the payer choose: a student paying a
    later instalment while an earlier one is outstanding is still in default
    on the earlier one, and allowing the choice hides that.
    """
    remaining = amount_minor
    settled: list[int] = []
    for instalment in sorted(plan.instalments, key=lambda row: row.sequence):
        if remaining <= 0:
            break
        if instalment.status in ("paid", "waived"):
            continue
        owed = instalment.amount_minor - instalment.paid_minor
        applied = min(owed, remaining)
        instalment.paid_minor += applied
        remaining -= applied
        if payment_id is not None and payment_id not in instalment.payment_ids:
            instalment.payment_ids = [*instalment.payment_ids, payment_id]
        if instalment.paid_minor >= instalment.amount_minor:
            instalment.status = "paid"
            instalment.settled_on = date.today()
            settled.append(instalment.sequence)
        else:
            instalment.status = "part_paid"
    session.flush()

    if all(row.status in ("paid", "waived") for row in plan.instalments):
        plan.status = "completed"
        plan.completed_at = utcnow()
        session.flush()
        emit(
            "payment_plan:complete",
            AuditCategory.FINANCE,
            resource_type="payment_plan",
            resource_id=plan.id,
            resource_label=plan.reference,
            summary="Plan completed",
        )
    return {"settled_instalments": settled, "unapplied_minor": remaining}


def review_plans(session: Session, *, on: date | None = None) -> dict[str, int]:
    """Mark missed instalments and default the plans that have run out of rope.

    Run daily. A plan that has quietly stopped being paid but still reads
    `active` protects a student from blocks they should be feeling, which is
    unfair to everyone paying.
    """
    today = on or date.today()
    overdue = (
        session.execute(
            select(PaymentPlanInstalment)
            .join(PaymentPlan, PaymentPlan.id == PaymentPlanInstalment.plan_id)
            .where(
                PaymentPlanInstalment.status.in_(("pending", "part_paid")),
                PaymentPlanInstalment.due_on < today,
                PaymentPlan.status == "active",
                PaymentPlanInstalment.deleted_at.is_(None),
            )
        )
        .scalars()
        .all()
    )

    missed = 0
    defaulted = 0
    touched: set[uuid.UUID] = set()
    for instalment in overdue:
        if instalment.status != "missed":
            instalment.status = "missed"
            missed += 1
        touched.add(instalment.plan_id)
    session.flush()

    for plan_id in touched:
        plan = session.get(PaymentPlan, plan_id)
        if plan is None or plan.status != "active":
            continue
        plan.missed_count = sum(1 for row in plan.instalments if row.status == "missed")
        if plan.missed_count > plan.missed_allowance:
            plan.status = "defaulted"
            plan.defaulted_at = utcnow()
            defaulted += 1
            emit(
                "payment_plan:default",
                AuditCategory.FINANCE,
                resource_type="payment_plan",
                resource_id=plan.id,
                resource_label=plan.reference,
                summary=(
                    f"Defaulted after {plan.missed_count} missed instalment(s); "
                    "surcharges and blocks resume"
                ),
                severity="warning",
            )
    session.flush()
    log.info("payment_plans_reviewed", missed=missed, defaulted=defaulted)
    return {"instalments_missed": missed, "plans_defaulted": defaulted}


# ---------------------------------------------------------------------------
# Surcharges
# ---------------------------------------------------------------------------


def applicable_rule(
    session: Session,
    *,
    academic_year_id: uuid.UUID | None,
    programme_id: uuid.UUID | None,
    sponsorship: str | None,
    invoice_kind: str,
    on: date,
) -> LatePaymentRule | None:
    """The most specific approved rule for this invoice, or none.

    Resolved specific-first — a rule naming this programme beats one naming
    only the year — and a `None` result means the institution has not decided
    to charge, which is a legitimate answer and not an error.
    """
    if academic_year_id is None:
        return None
    # `programme_id IN (:id, NULL)` would be wrong, and wrong silently: in SQL
    # nothing is ever `IN` a NULL, so the institution-wide rule — the one with
    # no programme — could never be selected, and every invoice would come
    # back with no rule at all. It has to be an explicit `IS NULL`.
    scope = (
        LatePaymentRule.programme_id.is_(None)
        if programme_id is None
        else or_(
            LatePaymentRule.programme_id == programme_id,
            LatePaymentRule.programme_id.is_(None),
        )
    )
    stmt = (
        select(LatePaymentRule)
        .where(
            LatePaymentRule.academic_year_id == academic_year_id,
            LatePaymentRule.status == "approved",
            LatePaymentRule.deleted_at.is_(None),
            LatePaymentRule.applies_to_invoice_kind.in_((invoice_kind, "all")),
            scope,
        )
        # Most specific first: a rule naming this programme beats one naming
        # only the year.
        .order_by(
            LatePaymentRule.programme_id.desc().nullslast(),
            LatePaymentRule.sponsorship.desc().nullslast(),
        )
    )
    for rule in session.execute(stmt).scalars():
        if rule.sponsorship is not None and rule.sponsorship != sponsorship:
            continue
        if rule.effective_from and on < rule.effective_from:
            continue
        if rule.effective_to and on > rule.effective_to:
            continue
        return rule
    return None


def surcharge_due(
    *, rule: LatePaymentRule, balance_minor: int, days_overdue: int, already_charged: int
) -> tuple[int, int]:
    """`(amount, sequence)` for the next surcharge, or `(0, 0)`.

    All the arithmetic in one place so the statement can show it. A charge a
    student cannot reconstruct is a charge they dispute, and they are usually
    right to.
    """
    if days_overdue <= rule.grace_days or balance_minor <= 0:
        return 0, 0
    chargeable_days = days_overdue - rule.grace_days

    if rule.recurrence == "once":
        periods = 1
    elif rule.recurrence == "weekly":
        periods = (chargeable_days + 6) // 7
    elif rule.recurrence == "monthly":
        periods = (chargeable_days + 29) // 30
    else:  # per_semester
        periods = 1
    if rule.max_charges is not None:
        periods = min(periods, rule.max_charges)
    if already_charged >= periods:
        return 0, 0

    if rule.charge_basis == "flat":
        per_charge = int(rule.charge_flat_minor or 0)
    else:
        percent = Decimal(str(rule.charge_percent or 0))
        per_charge = int(
            (Decimal(balance_minor) * percent / Decimal(100)).to_integral_value(
                rounding=ROUND_HALF_UP
            )
        )
    if per_charge <= 0:
        return 0, 0

    sequence = already_charged + 1
    if rule.charge_cap_minor is not None:
        charged_so_far = per_charge * already_charged
        headroom = rule.charge_cap_minor - charged_so_far
        if headroom <= 0:
            return 0, 0
        per_charge = min(per_charge, headroom)
    return per_charge, sequence


def apply_surcharges(
    session: Session,
    *,
    on: date | None = None,
    actor_id: uuid.UUID | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """The nightly late-payment run.

    Skips any invoice protected by an active plan, and posts each surcharge
    as a real invoice line and a real ledger entry — a surcharge that exists
    only as a number on a statement is one the ledger cannot explain.
    """
    today = on or date.today()
    overdue_invoices = (
        session.execute(
            select(Invoice).where(
                Invoice.status.in_(("issued", "part_paid", "overdue")),
                Invoice.balance_minor > 0,
                Invoice.due_on.is_not(None),
                Invoice.due_on < today,
                Invoice.student_id.is_not(None),
                Invoice.deleted_at.is_(None),
            )
        )
        .scalars()
        .all()
    )

    applied: list[dict[str, Any]] = []
    skipped_under_plan = 0
    no_rule = 0

    for invoice in overdue_invoices:
        if invoice.due_on is None or invoice.student_id is None:  # pragma: no cover
            continue
        if under_active_plan(session, invoice_id=invoice.id) is not None:
            skipped_under_plan += 1
            continue

        rule = applicable_rule(
            session,
            academic_year_id=_academic_year_of(session, invoice=invoice),
            programme_id=None,
            sponsorship=None,
            invoice_kind=invoice.kind,
            on=today,
        )
        if rule is None:
            no_rule += 1
            continue

        already = int(
            session.execute(
                select(func.count()).where(
                    PenaltyCharge.invoice_id == invoice.id,
                    PenaltyCharge.rule_id == rule.id,
                    PenaltyCharge.status == "applied",
                    PenaltyCharge.deleted_at.is_(None),
                )
            ).scalar_one()
        )
        days = (today - invoice.due_on).days
        amount, sequence = surcharge_due(
            rule=rule,
            balance_minor=invoice.balance_minor,
            days_overdue=days,
            already_charged=already,
        )
        if amount <= 0:
            continue
        if dry_run:
            applied.append(
                {
                    "invoice": invoice.number,
                    "amount_minor": amount,
                    "days_overdue": days,
                    "rule": rule.code,
                }
            )
            continue

        charge = _post_surcharge(
            session,
            invoice=invoice,
            rule=rule,
            amount_minor=amount,
            days_overdue=days,
            sequence=sequence,
            actor_id=actor_id,
            automatic=True,
        )
        applied.append(
            {
                "invoice": invoice.number,
                "amount_minor": charge.amount_minor,
                "days_overdue": days,
                "rule": rule.code,
            }
        )

    log.info(
        "surcharges_applied",
        charged=len(applied),
        skipped_under_plan=skipped_under_plan,
        no_rule=no_rule,
        dry_run=dry_run,
    )
    return {
        "charged": len(applied),
        "total_minor": sum(row["amount_minor"] for row in applied),
        "skipped_under_plan": skipped_under_plan,
        "invoices_with_no_rule": no_rule,
        "charges": applied[:100],
        "dry_run": dry_run,
    }


def _academic_year_of(session: Session, *, invoice: Invoice) -> uuid.UUID | None:
    """The academic year an invoice belongs to, through its semester."""
    from acmis.modules.shared.models import Semester

    if invoice.semester_id is None:
        return None
    semester = session.get(Semester, invoice.semester_id)
    return semester.academic_year_id if semester is not None else None


def _post_surcharge(
    session: Session,
    *,
    invoice: Invoice,
    rule: LatePaymentRule,
    amount_minor: int,
    days_overdue: int,
    sequence: int,
    actor_id: uuid.UUID | None,
    automatic: bool,
) -> PenaltyCharge:
    """Add the money to the invoice and the ledger, and record why."""
    line = InvoiceLine(
        invoice_id=invoice.id,
        code=rule.charge_fee_item_code or "LATE-FEE",
        description=(
            f"Late payment surcharge ({days_overdue} day(s) past due"
            + (f", charge {sequence}" if sequence > 1 else "")
            + ")"
        ),
        category="penalty",
        quantity=1,
        unit_amount_minor=amount_minor,
        amount_minor=amount_minor,
        payable_by="student",
        gl_account_code=ACCOUNT_FEE_INCOME,
        created_by_id=actor_id,
    )
    session.add(line)
    invoice.subtotal_minor += amount_minor
    invoice.total_minor += amount_minor
    invoice.balance_minor += amount_minor
    session.flush()

    charge = PenaltyCharge(
        student_id=invoice.student_id,
        invoice_id=invoice.id,
        rule_id=rule.id,
        invoice_line_id=line.id,
        charged_on=date.today(),
        days_overdue=days_overdue,
        balance_at_charge_minor=invoice.balance_minor - amount_minor,
        percent_applied=rule.charge_percent if rule.charge_basis == "percentage" else None,
        amount_minor=amount_minor,
        sequence=sequence,
        status="applied",
        applied_by_id=actor_id,
        applied_automatically=automatic,
        created_by_id=actor_id,
    )
    session.add(charge)
    session.flush()

    post_transaction(
        session,
        legs=[
            (
                ACCOUNT_STUDENT_RECEIVABLE,
                amount_minor,
                f"{invoice.number} late payment surcharge",
            ),
            (ACCOUNT_FEE_INCOME, -amount_minor, f"{invoice.number} surcharge income"),
        ],
        student_id=invoice.student_id,
        source_type="penalty_charge",
        source_id=charge.id,
        value_date=date.today(),
        actor_id=actor_id,
    )
    if invoice.student_id is not None:
        recompute_balance(session, student_id=invoice.student_id)
    emit(
        "penalty_charge:apply",
        AuditCategory.FINANCE,
        resource_type="penalty_charge",
        resource_id=charge.id,
        summary=(
            f"Surcharge of {amount_minor / 100:,.0f} on {invoice.number} "
            f"({days_overdue} day(s) past due, rule {rule.code})"
        ),
        metadata={"rule": rule.code, "days_overdue": days_overdue},
    )
    return charge


def reverse_surcharge(
    session: Session, *, charge: PenaltyCharge, reason: str, actor_id: uuid.UUID | None
) -> PenaltyCharge:
    """Take a surcharge back off, leaving both entries visible.

    The commonest reason is a payment that had not yet been posted when the
    job ran — the student paid on time and the bank was slow, and they should
    not carry the cost of the float.
    """
    if charge.status != "applied":
        raise Conflict(f"This surcharge is already {charge.status}.")
    invoice = session.get(Invoice, charge.invoice_id)
    if invoice is None:  # pragma: no cover
        raise Conflict("The invoice for this surcharge no longer exists.")

    charge.status = "reversed"
    charge.reversed_at = utcnow()
    charge.reversed_by_id = actor_id
    charge.reversal_reason = reason
    invoice.subtotal_minor -= charge.amount_minor
    invoice.total_minor -= charge.amount_minor
    invoice.balance_minor -= charge.amount_minor
    session.flush()

    post_transaction(
        session,
        legs=[
            (
                ACCOUNT_STUDENT_RECEIVABLE,
                -charge.amount_minor,
                f"{invoice.number} surcharge reversed",
            ),
            (
                ACCOUNT_FEE_INCOME,
                charge.amount_minor,
                f"{invoice.number} surcharge reversal",
            ),
        ],
        student_id=charge.student_id,
        source_type="penalty_charge",
        source_id=charge.id,
        value_date=date.today(),
        actor_id=actor_id,
    )
    recompute_balance(session, student_id=charge.student_id)
    emit(
        "penalty_charge:reverse",
        AuditCategory.FINANCE,
        resource_type="penalty_charge",
        resource_id=charge.id,
        summary=f"Surcharge of {charge.amount_minor / 100:,.0f} reversed: {reason}",
        severity="notice",
        metadata={"reason": reason},
    )
    return charge


# ---------------------------------------------------------------------------
# Reminders
# ---------------------------------------------------------------------------


def send_reminders(
    session: Session,
    *,
    on: date | None = None,
    actor_id: uuid.UUID | None = None,
    channel: str = "email",
) -> dict[str, Any]:
    """Walk the escalation ladder. Run daily.

    One notice per student per level, ever. A ladder with no memory emails the
    same student every night, which trains them to filter it — and then the
    notice that mattered goes unread.
    """
    today = on or date.today()
    invoices = (
        session.execute(
            select(Invoice).where(
                Invoice.status.in_(("issued", "part_paid", "overdue")),
                Invoice.balance_minor > 0,
                Invoice.due_on.is_not(None),
                Invoice.due_on < today,
                Invoice.student_id.is_not(None),
                Invoice.deleted_at.is_(None),
            )
        )
        .scalars()
        .all()
    )

    sent: list[dict[str, Any]] = []
    for invoice in invoices:
        if invoice.due_on is None or invoice.student_id is None:  # pragma: no cover
            continue
        if under_active_plan(session, invoice_id=invoice.id) is not None:
            continue
        days = (today - invoice.due_on).days
        due_level = 0
        consequence = ""
        for level, threshold, wording in DUNNING_LADDER:
            if days >= threshold:
                due_level, consequence = level, wording
        if due_level == 0:
            continue

        highest = int(
            session.execute(
                select(func.coalesce(func.max(DunningNotice.level), 0)).where(
                    DunningNotice.invoice_id == invoice.id,
                    DunningNotice.deleted_at.is_(None),
                )
            ).scalar_one()
        )
        if highest >= due_level:
            continue

        notice = DunningNotice(
            student_id=invoice.student_id,
            invoice_id=invoice.id,
            level=due_level,
            channel=channel,
            sent_on=today,
            sent_at=utcnow(),
            balance_minor=invoice.balance_minor,
            days_overdue=days,
            consequence_stated=consequence,
            # A government-sponsored student's arrears are the sponsor's
            # problem; chasing the student for them is futile and unkind.
            sent_to_sponsor=invoice.sponsor_portion_minor > 0,
            sent_by_id=actor_id,
            created_by_id=actor_id,
        )
        session.add(notice)
        session.flush()
        emit(
            "dunning_notice:send",
            AuditCategory.FINANCE,
            resource_type="dunning_notice",
            resource_id=notice.id,
            summary=(
                f"Level {due_level} reminder on {invoice.number}: "
                f"{invoice.balance_minor / 100:,.0f} outstanding, {days} day(s) past due"
            ),
            metadata={"level": due_level, "days_overdue": days},
        )
        sent.append(
            {
                "invoice": invoice.number,
                "level": due_level,
                "days_overdue": days,
                "balance_minor": invoice.balance_minor,
            }
        )

    log.info("dunning_run", sent=len(sent))
    return {"sent": len(sent), "notices": sent[:100]}


def block_state(session: Session, *, student_id: uuid.UUID) -> dict[str, Any]:
    """What, if anything, is currently blocked for this student, and why.

    The answer a registry clerk and the student both need, in one shape: not
    "blocked" but which gate, under which rule, and what would lift it.
    """
    invoices = (
        session.execute(
            select(Invoice).where(
                Invoice.student_id == student_id,
                Invoice.balance_minor > 0,
                Invoice.deleted_at.is_(None),
            )
        )
        .scalars()
        .all()
    )

    today = date.today()
    blocks: list[dict[str, Any]] = []
    protected_by_plan = False

    for invoice in invoices:
        if invoice.due_on is None:
            continue
        plan = under_active_plan(session, invoice_id=invoice.id)
        if plan is not None:
            protected_by_plan = True
            continue
        days = (today - invoice.due_on).days
        if days <= 0:
            continue
        rule = applicable_rule(
            session,
            academic_year_id=_academic_year_of(session, invoice=invoice),
            programme_id=None,
            sponsorship=None,
            invoice_kind=invoice.kind,
            on=today,
        )
        if rule is None:
            continue
        for gate, threshold in (
            ("registration", rule.blocks_registration_after_days),
            ("exam_card", rule.blocks_exam_card_after_days),
            ("results", rule.blocks_results_after_days),
        ):
            if threshold is not None and days >= threshold:
                blocks.append(
                    {
                        "gate": gate,
                        "invoice": invoice.number,
                        "days_overdue": days,
                        "rule": rule.code,
                        "waivable": rule.is_waivable,
                        "clears_when": (
                            f"the balance of {invoice.balance_minor / 100:,.0f} is settled, "
                            "or a payment plan is agreed"
                        ),
                    }
                )

    return {
        "student_id": str(student_id),
        "blocked": bool(blocks),
        "protected_by_plan": protected_by_plan,
        "blocks": blocks,
    }
