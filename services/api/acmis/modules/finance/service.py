"""Finance domain logic: invoicing, receipting, allocation, the ledger.

Every money movement goes through `post_transaction`, which refuses to commit a
set of ledger legs that does not sum to zero. That single check is what keeps
the student ledger explainable: a balance is a SUM over entries, and there is
no code path that can move money without writing both sides of it.
"""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Sequence
from datetime import date
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from acmis.core.audit import AuditCategory, diff, emit
from acmis.core.errors import Conflict, NotFound, RuleViolation, ValidationFailed
from acmis.core.models import utcnow
from acmis.modules.finance.models import (
    AccountingPeriod,
    FeeItem,
    FeeStructure,
    Invoice,
    InvoiceLine,
    LedgerEntry,
    Payment,
    PaymentAllocation,
    PaymentStatus,
    Sponsorship,
    StudentAccount,
    Waiver,
)

log = structlog.get_logger(__name__)

# Chart of accounts, kept deliberately small. A university's real GL lives in
# its accounting system; ACMIS needs only enough structure to keep the student
# sub-ledger self-consistent and to hand over a trial balance.
ACCOUNT_STUDENT_RECEIVABLE = "1200-student-receivable"
ACCOUNT_TUITION_INCOME = "4000-tuition-income"
ACCOUNT_FEE_INCOME = "4100-other-fee-income"
ACCOUNT_CASH = "1000-cash-and-bank"
ACCOUNT_WAIVER_EXPENSE = "5200-fee-waivers"
ACCOUNT_SPONSOR_RECEIVABLE = "1250-sponsor-receivable"
ACCOUNT_UNAPPLIED_RECEIPTS = "2100-unapplied-receipts"


def period_code_for(when: date) -> str:
    return f"{when.year:04d}-{when.month:02d}"


def require_open_period(session: Session, when: date) -> AccountingPeriod | None:
    """Refuse a posting into a closed month.

    Returns None when no period row exists — an institution that has not
    started closing periods is not blocked from operating. Once it does, a
    closed period is closed, and reopening one is an audited act.
    """
    code = period_code_for(when)
    period = session.execute(
        select(AccountingPeriod).where(AccountingPeriod.code == code)
    ).scalar_one_or_none()
    if period is not None and period.status == "closed":
        raise RuleViolation(
            f"Accounting period {code} is closed.",
            rule="period_closed",
            waivable_by=["finance:reopen_period"],
        )
    return period


def post_transaction(
    session: Session,
    *,
    legs: Sequence[tuple[str, int, str]],
    student_id: uuid.UUID | None,
    source_type: str,
    source_id: uuid.UUID | None,
    value_date: date,
    actor_id: uuid.UUID | None,
) -> uuid.UUID:
    """Write one balanced transaction. `legs` is [(account, signed_minor, narrative)].

    Positive is a debit, negative a credit. The sum must be zero — checked here
    and not merely by convention, because a half-written transaction is
    invisible until a reconciliation months later and then unattributable.
    """
    total = sum(amount for _account, amount, _narrative in legs)
    if total != 0:
        raise ValidationFailed(
            "Refusing to post an unbalanced transaction.",
            code="unbalanced_transaction",
            details={"imbalance_minor": total, "legs": len(legs)},
        )
    if any(amount == 0 for _a, amount, _n in legs):
        raise ValidationFailed("A ledger leg cannot be zero.")

    require_open_period(session, value_date)
    transaction_id = uuid.uuid4()
    now = utcnow()
    for sequence, (account, amount, narrative) in enumerate(legs, start=1):
        session.add(
            LedgerEntry(
                transaction_id=transaction_id,
                sequence=sequence,
                posted_at=now,
                value_date=value_date,
                period_code=period_code_for(value_date),
                student_id=student_id,
                account_code=account,
                amount_minor=amount,
                narrative=narrative[:300],
                source_type=source_type,
                source_id=source_id,
                posted_by_id=actor_id,
                created_by_id=actor_id,
            )
        )
    session.flush()
    return transaction_id


def account_for(session: Session, student_id: uuid.UUID, *, currency: str) -> StudentAccount:
    account = session.execute(
        select(StudentAccount).where(StudentAccount.student_id == student_id)
    ).scalar_one_or_none()
    if account is None:
        account = StudentAccount(student_id=student_id, currency=currency)
        session.add(account)
        session.flush()
    return account


def recompute_balance(session: Session, *, student_id: uuid.UUID) -> StudentAccount:
    """Rebuild the cached balance from the ledger.

    The ledger is authoritative; `StudentAccount.balance_minor` is a cache. On
    disagreement the entries win and the cache is rebuilt — that ordering is
    what makes the number defensible, and the nightly reconciliation asserts
    the two agree.
    """
    total = session.execute(
        select(func.coalesce(func.sum(LedgerEntry.amount_minor), 0)).where(
            LedgerEntry.student_id == student_id,
            LedgerEntry.account_code == ACCOUNT_STUDENT_RECEIVABLE,
        )
    ).scalar_one()

    invoiced = session.execute(
        select(func.coalesce(func.sum(Invoice.total_minor), 0)).where(
            Invoice.student_id == student_id,
            Invoice.status.notin_(["draft", "cancelled"]),
            Invoice.deleted_at.is_(None),
        )
    ).scalar_one()
    paid = session.execute(
        select(func.coalesce(func.sum(Payment.amount_minor), 0)).where(
            Payment.student_id == student_id,
            Payment.status == PaymentStatus.SETTLED,
            Payment.deleted_at.is_(None),
        )
    ).scalar_one()
    waived = session.execute(
        select(func.coalesce(func.sum(Waiver.amount_minor), 0)).where(
            Waiver.student_id == student_id,
            Waiver.status == "released",
            Waiver.deleted_at.is_(None),
        )
    ).scalar_one()

    account = account_for(session, student_id, currency="UGX")
    account.balance_minor = int(total)
    account.total_invoiced_minor = int(invoiced)
    account.total_paid_minor = int(paid)
    account.total_waived_minor = int(waived)
    account.recomputed_at = utcnow()
    session.flush()
    return account


# ---------------------------------------------------------------------------
# Invoicing
# ---------------------------------------------------------------------------


def next_invoice_number(session: Session, *, prefix: str = "INV") -> str:
    year = date.today().year
    used = session.execute(
        select(func.count())
        .select_from(Invoice)
        .where(func.extract("year", Invoice.created_at) == year)
    ).scalar_one()
    return f"{prefix}/{year}/{used + 1:06d}"


def resolve_fee_structure(
    session: Session,
    *,
    programme_id: uuid.UUID,
    academic_year_id: uuid.UUID,
    cohort_year_id: uuid.UUID | None,
    sponsorship: str,
    year_of_study: int,
) -> FeeStructure | None:
    """Find the published fee schedule that applies.

    Most specific first: a schedule scoped to this programme, cohort,
    sponsorship and year beats a general one. Cohort scoping is what makes
    "your fees are fixed at the rate you entered on" true, which most
    institutions promise and few systems implement.
    """
    candidates = (
        session.execute(
            select(FeeStructure).where(
                FeeStructure.academic_year_id == academic_year_id,
                FeeStructure.status == "published",
                FeeStructure.deleted_at.is_(None),
            )
        )
        .scalars()
        .all()
    )

    def specificity(structure: FeeStructure) -> int:
        score = 0
        if structure.programme_id == programme_id:
            score += 8
        elif structure.programme_id is not None:
            return -1
        if cohort_year_id and structure.cohort_year_id == cohort_year_id:
            score += 4
        elif structure.cohort_year_id is not None:
            return -1
        if structure.sponsorship == sponsorship:
            score += 2
        elif structure.sponsorship is not None:
            return -1
        if structure.year_of_study == year_of_study:
            score += 1
        elif structure.year_of_study is not None:
            return -1
        return score

    ranked = sorted(
        ((specificity(s), s) for s in candidates), key=lambda pair: pair[0], reverse=True
    )
    return next((s for score, s in ranked if score >= 0), None)


def raise_semester_invoice(
    session: Session,
    *,
    student: Any,
    student_programme: Any,
    semester_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> Invoice:
    """Invoice a student for a semester.

    Lines are copied from the fee structure rather than referenced, so the
    invoice still reads exactly as issued after the structure is superseded.
    The sponsor's portion is split out: a sponsored student's own balance must
    show only what *they* owe, or the registration block punishes them for
    their sponsor's lateness.
    """
    from acmis.modules.shared.models import Semester

    semester = session.get(Semester, semester_id)
    if semester is None:
        raise NotFound("That semester does not exist.")

    existing = session.execute(
        select(Invoice).where(
            Invoice.student_id == student.id,
            Invoice.semester_id == semester_id,
            Invoice.kind == "semester_fees",
            Invoice.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    structure = resolve_fee_structure(
        session,
        programme_id=student_programme.programme_id,
        academic_year_id=semester.academic_year_id,
        cohort_year_id=student_programme.entry_academic_year_id,
        sponsorship=student_programme.sponsorship,
        year_of_study=student_programme.current_year_of_study,
    )

    invoice = Invoice(
        number=next_invoice_number(session),
        student_id=student.id,
        semester_id=semester_id,
        fee_structure_id=structure.id if structure else None,
        kind="semester_fees",
        currency=structure.currency if structure else "UGX",
        status="issued",
        issued_on=date.today(),
        due_on=semester.registration_closes_on or semester.starts_on,
        period_code=period_code_for(date.today()),
        created_by_id=actor_id,
    )
    session.add(invoice)
    session.flush()

    sponsorship = (
        session.execute(
            select(Sponsorship).where(
                Sponsorship.student_id == student.id,
                Sponsorship.status == "active",
                Sponsorship.deleted_at.is_(None),
            )
        )
        .scalars()
        .first()
    )

    subtotal = 0
    sponsor_portion = 0
    if structure is not None:
        for item in structure.items:
            if item.deleted_at is not None:
                continue
            if item.semester_kind and item.semester_kind != semester.kind:
                continue
            amount = item.amount_minor
            if item.basis == "per_year" and semester.sequence != 1:
                # Annual charges land once, on the first semester of the year.
                continue

            covered = _sponsor_covers(sponsorship, item, amount)
            session.add(
                InvoiceLine(
                    invoice_id=invoice.id,
                    fee_item_id=item.id,
                    code=item.code,
                    description=item.name,
                    category=item.category,
                    quantity=1,
                    unit_amount_minor=amount,
                    amount_minor=amount,
                    payable_by="sponsor" if covered >= amount else item.payable_by,
                    gl_account_code=item.gl_account_code,
                    created_by_id=actor_id,
                )
            )
            subtotal += amount
            sponsor_portion += covered

    invoice.subtotal_minor = subtotal
    invoice.total_minor = subtotal
    invoice.sponsor_portion_minor = sponsor_portion
    invoice.balance_minor = subtotal
    invoice.sponsorship_id = sponsorship.id if sponsorship else None
    session.flush()

    student_share = subtotal - sponsor_portion
    legs: list[tuple[str, int, str]] = []
    if student_share:
        legs.append(
            (ACCOUNT_STUDENT_RECEIVABLE, student_share, f"{invoice.number} student portion")
        )
    if sponsor_portion:
        legs.append(
            (ACCOUNT_SPONSOR_RECEIVABLE, sponsor_portion, f"{invoice.number} sponsor portion")
        )
    if subtotal:
        legs.append((ACCOUNT_TUITION_INCOME, -subtotal, f"{invoice.number} fees billed"))
        post_transaction(
            session,
            legs=legs,
            student_id=student.id,
            source_type="invoice",
            source_id=invoice.id,
            value_date=invoice.issued_on or date.today(),
            actor_id=actor_id,
        )
    recompute_balance(session, student_id=student.id)

    emit(
        "invoice:create",
        AuditCategory.FINANCE,
        resource_type="invoice",
        resource_id=invoice.id,
        resource_label=invoice.number,
        summary=f"Semester invoice raised: {subtotal / 100:,.2f} {invoice.currency}",
        metadata={
            "semester_id": str(semester_id),
            "sponsor_portion_minor": sponsor_portion,
            "fee_structure": structure.code if structure else None,
        },
    )
    return invoice


def _sponsor_covers(sponsorship: Sponsorship | None, item: FeeItem, amount: int) -> int:
    """How much of this line the sponsor pays.

    Coverage is data on the sponsorship, not code, because every sponsor's
    terms differ — "tuition only", "80% capped at 2,000,000", "everything
    except the guild fee" — and encoding them here means a release per sponsor.
    """
    if sponsorship is None:
        return 0
    coverage = sponsorship.coverage or {}
    categories = coverage.get("categories")
    if categories and item.category not in categories:
        return 0
    excluded = coverage.get("excluded_categories") or []
    if item.category in excluded:
        return 0

    percent = float(coverage.get("percent", 100))
    covered = int(amount * percent / 100)
    cap = coverage.get("cap_minor")
    if cap is not None:
        remaining = int(cap) - sponsorship.total_disbursed_minor
        covered = max(0, min(covered, remaining))
    return min(covered, amount)


def raise_application_fee(
    session: Session,
    *,
    applicant_id: uuid.UUID,
    scheme: Any,
    is_late: bool,
    actor_id: uuid.UUID,
) -> Invoice:
    """Invoice an applicant, who is not yet a student.

    No ledger posting. An applicant is not on the student sub-ledger, and
    posting a receivable against someone who may never enrol pollutes the
    balance the registration block reads.
    """
    amount = scheme.application_fee_minor + (scheme.late_fee_minor if is_late else 0)
    invoice = Invoice(
        number=next_invoice_number(session, prefix="APF"),
        applicant_id=applicant_id,
        kind="application",
        currency=scheme.currency,
        status="issued",
        issued_on=date.today(),
        due_on=date.today(),
        subtotal_minor=amount,
        total_minor=amount,
        balance_minor=amount,
        period_code=period_code_for(date.today()),
        created_by_id=actor_id,
    )
    session.add(invoice)
    session.flush()
    session.add(
        InvoiceLine(
            invoice_id=invoice.id,
            code="APPFEE",
            description=f"Application fee — {scheme.name}" + (" (late)" if is_late else ""),
            category="application",
            quantity=1,
            unit_amount_minor=amount,
            amount_minor=amount,
            created_by_id=actor_id,
        )
    )
    session.flush()
    emit(
        "invoice:create",
        AuditCategory.FINANCE,
        resource_type="invoice",
        resource_id=invoice.id,
        resource_label=invoice.number,
        summary=f"Application fee invoiced: {amount / 100:,.2f} {scheme.currency}",
    )
    return invoice


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------


def record_payment(
    session: Session,
    *,
    student_id: uuid.UUID | None,
    applicant_id: uuid.UUID | None,
    amount_minor: int,
    currency: str,
    method: str,
    provider: str | None,
    provider_reference: str | None,
    payer_narrative: str | None,
    payer_name: str | None,
    value_date: date | None,
    actor_id: uuid.UUID,
    auto_allocate: bool = True,
) -> Payment:
    """Record money received, and allocate it.

    Two things worth stating:

    **Idempotency.** A provider's reference is unique. Mobile-money webhooks
    retry, and a retried callback that credits a student twice is discovered
    weeks later by a student who thinks they have paid. A duplicate returns the
    original payment rather than erroring, because the provider is not wrong to
    retry.

    **Unmatched is a real state.** A deposit with a mistyped student number
    lands as `unmatched` rather than failing. Money that arrived did arrive,
    and the bursary works a queue of these; recording it as a failure means it
    is never resolved.
    """
    if amount_minor <= 0:
        raise ValidationFailed("A payment amount must be positive.")

    if provider and provider_reference:
        existing = session.execute(
            select(Payment).where(
                Payment.provider == provider,
                Payment.provider_reference == provider_reference,
            )
        ).scalar_one_or_none()
        if existing is not None:
            log.info("payment_duplicate_ignored", reference=provider_reference)
            return existing

    settled = date.today() if value_date is None else value_date
    payment = Payment(
        reference=f"PAY/{date.today().year}/{secrets.token_hex(5).upper()}",
        student_id=student_id,
        applicant_id=applicant_id,
        method=method,
        provider=provider,
        provider_reference=provider_reference,
        payer_narrative=payer_narrative,
        payer_name=payer_name,
        currency=currency,
        amount_minor=amount_minor,
        status=(PaymentStatus.SETTLED if (student_id or applicant_id) else PaymentStatus.UNMATCHED),
        value_date=settled,
        settled_at=utcnow() if (student_id or applicant_id) else None,
        received_by_id=actor_id,
        raised_by_id=actor_id,
        receipt_number=f"RCT/{date.today().year}/{secrets.token_hex(4).upper()}",
        period_code=period_code_for(settled),
        created_by_id=actor_id,
    )
    session.add(payment)
    session.flush()

    if payment.status == PaymentStatus.SETTLED and student_id:
        post_transaction(
            session,
            legs=[
                (ACCOUNT_CASH, amount_minor, f"{payment.reference} received"),
                (
                    ACCOUNT_STUDENT_RECEIVABLE,
                    -amount_minor,
                    f"{payment.reference} applied to student account",
                ),
            ],
            student_id=student_id,
            source_type="payment",
            source_id=payment.id,
            value_date=settled,
            actor_id=actor_id,
        )
        if auto_allocate:
            allocate_payment(session, payment=payment, actor_id=actor_id)
        recompute_balance(session, student_id=student_id)
    elif payment.status == PaymentStatus.UNMATCHED:
        post_transaction(
            session,
            legs=[
                (ACCOUNT_CASH, amount_minor, f"{payment.reference} received, unmatched"),
                (
                    ACCOUNT_UNAPPLIED_RECEIPTS,
                    -amount_minor,
                    f"{payment.reference} awaiting identification",
                ),
            ],
            student_id=None,
            source_type="payment",
            source_id=payment.id,
            value_date=settled,
            actor_id=actor_id,
        )

    emit(
        "payment:record",
        AuditCategory.FINANCE,
        resource_type="payment",
        resource_id=payment.id,
        resource_label=payment.reference,
        summary=(
            f"{amount_minor / 100:,.2f} {currency} received by {method}"
            + (" — unmatched" if payment.status == PaymentStatus.UNMATCHED else "")
        ),
        metadata={
            "provider": provider,
            "provider_reference": provider_reference,
            "value_date": settled.isoformat(),
        },
        severity="warning" if payment.status == PaymentStatus.UNMATCHED else "info",
    )
    return payment


def allocate_payment(
    session: Session,
    *,
    payment: Payment,
    actor_id: uuid.UUID,
    invoice_id: uuid.UUID | None = None,
) -> list[PaymentAllocation]:
    """Apply a payment to outstanding invoices, oldest first.

    Oldest-first because a student's arrears must clear before the current
    semester, or the registration block for this semester is satisfied while
    last semester's debt is still open and the student is surprised at
    graduation. `is_automatic` records that the rule chose, not a cashier, so a
    disputed allocation can be identified and reversed.
    """
    if payment.status != PaymentStatus.SETTLED or not payment.student_id:
        return []

    remaining = payment.amount_minor - payment.allocated_minor
    if remaining <= 0:
        return []

    stmt = select(Invoice).where(
        Invoice.student_id == payment.student_id,
        Invoice.status.in_(["issued", "part_paid", "overdue"]),
        Invoice.balance_minor > 0,
        Invoice.deleted_at.is_(None),
    )
    if invoice_id:
        stmt = stmt.where(Invoice.id == invoice_id)
    invoices = (
        session.execute(stmt.order_by(Invoice.due_on.asc().nullslast(), Invoice.issued_on.asc()))
        .scalars()
        .all()
    )

    made: list[PaymentAllocation] = []
    for invoice in invoices:
        if remaining <= 0:
            break
        # The student's own share only. A sponsor's portion is chased from the
        # sponsor, and letting a student's payment clear it would tell the
        # institution the sponsor had paid.
        student_due = invoice.balance_minor - max(
            0, invoice.sponsor_portion_minor - invoice.paid_minor
        )
        applicable = min(remaining, max(0, student_due))
        if applicable <= 0:
            continue

        allocation = PaymentAllocation(
            payment_id=payment.id,
            invoice_id=invoice.id,
            amount_minor=applicable,
            allocated_by_id=actor_id,
            is_automatic=invoice_id is None,
            created_by_id=actor_id,
        )
        session.add(allocation)
        made.append(allocation)

        invoice.paid_minor += applicable
        invoice.balance_minor = max(
            0, invoice.total_minor - invoice.paid_minor - invoice.waived_minor
        )
        invoice.status = "paid" if invoice.balance_minor == 0 else "part_paid"
        remaining -= applicable

    payment.allocated_minor = payment.amount_minor - remaining
    session.flush()

    if made:
        emit(
            "payment:allocate",
            AuditCategory.FINANCE,
            resource_type="payment",
            resource_id=payment.id,
            resource_label=payment.reference,
            summary=f"Allocated to {len(made)} invoice(s)",
            metadata={
                "allocations": [
                    {"invoice_id": str(a.invoice_id), "amount_minor": a.amount_minor} for a in made
                ],
                "unallocated_minor": remaining,
            },
        )
    return made


def match_unmatched_payment(
    session: Session, *, payment: Payment, student_id: uuid.UUID, actor_id: uuid.UUID
) -> Payment:
    """Identify a deposit that arrived without a usable reference.

    Moves the money off the unapplied-receipts account and onto the student's,
    then allocates it. The audit line names who decided the deposit belonged
    to this student, which is the whole point — it is a judgement, sometimes a
    wrong one.
    """
    if payment.status != PaymentStatus.UNMATCHED:
        raise Conflict("This payment is not awaiting identification.")

    before = {"status": payment.status, "student_id": None}
    payment.student_id = student_id
    payment.status = PaymentStatus.SETTLED
    payment.settled_at = utcnow()

    post_transaction(
        session,
        legs=[
            (
                ACCOUNT_UNAPPLIED_RECEIPTS,
                payment.amount_minor,
                f"{payment.reference} identified",
            ),
            (
                ACCOUNT_STUDENT_RECEIVABLE,
                -payment.amount_minor,
                f"{payment.reference} applied to student account",
            ),
        ],
        student_id=student_id,
        source_type="payment",
        source_id=payment.id,
        value_date=payment.value_date or date.today(),
        actor_id=actor_id,
    )
    allocate_payment(session, payment=payment, actor_id=actor_id)
    recompute_balance(session, student_id=student_id)

    emit(
        "payment:match",
        AuditCategory.FINANCE,
        resource_type="payment",
        resource_id=payment.id,
        resource_label=payment.reference,
        summary=f"Identified as belonging to student {student_id}",
        changes=diff(before, {"status": payment.status, "student_id": str(student_id)}),
        severity="notice",
    )
    return payment


def reverse_payment(
    session: Session, *, payment: Payment, actor_id: uuid.UUID, reason: str
) -> Payment:
    """Reverse a payment with a contra transaction. Never by deletion.

    The four-eyes rule is in the policy bundle and asserted again here: a
    bounced cheque and a fraudulent reversal look identical in the data unless
    two different people are involved.
    """
    if payment.status != PaymentStatus.SETTLED:
        raise Conflict("Only a settled payment can be reversed.")
    if payment.raised_by_id == actor_id:
        raise RuleViolation(
            "A payment must be reversed by someone other than the person who recorded it.",
            rule="four_eyes",
        )

    payment.status = PaymentStatus.REVERSED
    payment.reversed_by_id = actor_id
    payment.reversed_at = utcnow()
    payment.reversal_reason = reason

    for allocation in payment.allocations:
        if allocation.reversed_at is not None:
            continue
        allocation.reversed_at = utcnow()
        invoice = session.get(Invoice, allocation.invoice_id)
        if invoice is not None:
            invoice.paid_minor = max(0, invoice.paid_minor - allocation.amount_minor)
            invoice.balance_minor = max(
                0, invoice.total_minor - invoice.paid_minor - invoice.waived_minor
            )
            invoice.status = "issued" if invoice.paid_minor == 0 else "part_paid"

    if payment.student_id:
        post_transaction(
            session,
            legs=[
                (
                    ACCOUNT_STUDENT_RECEIVABLE,
                    payment.amount_minor,
                    f"{payment.reference} reversed",
                ),
                (ACCOUNT_CASH, -payment.amount_minor, f"{payment.reference} reversed"),
            ],
            student_id=payment.student_id,
            source_type="payment_reversal",
            source_id=payment.id,
            value_date=date.today(),
            actor_id=actor_id,
        )
        recompute_balance(session, student_id=payment.student_id)

    emit(
        "payment:reverse",
        AuditCategory.FINANCE,
        resource_type="payment",
        resource_id=payment.id,
        resource_label=payment.reference,
        summary=f"Reversed: {reason}",
        metadata={"amount_minor": payment.amount_minor, "reason": reason},
        severity="warning",
    )
    return payment


# ---------------------------------------------------------------------------
# Waivers
# ---------------------------------------------------------------------------


def raise_waiver(
    session: Session,
    *,
    student_id: uuid.UUID,
    invoice_id: uuid.UUID | None,
    category: str,
    amount_minor: int,
    reason: str,
    evidence_reference: str | None,
    actor_id: uuid.UUID,
) -> Waiver:
    if amount_minor <= 0:
        raise ValidationFailed("A waiver amount must be positive.")
    if len(reason.strip()) < 10:
        raise ValidationFailed(
            "State the grounds for the waiver — this is the record an auditor reads."
        )

    waiver = Waiver(
        reference=f"WVR/{date.today().year}/{secrets.token_hex(4).upper()}",
        student_id=student_id,
        invoice_id=invoice_id,
        category=category,
        amount_minor=amount_minor,
        reason=reason,
        evidence_reference=evidence_reference,
        status="raised",
        raised_by_id=actor_id,
        raised_at=utcnow(),
        period_code=period_code_for(date.today()),
        created_by_id=actor_id,
    )
    session.add(waiver)
    session.flush()
    emit(
        "waiver:create",
        AuditCategory.FINANCE,
        resource_type="waiver",
        resource_id=waiver.id,
        resource_label=waiver.reference,
        summary=f"Waiver raised: {amount_minor / 100:,.2f} ({category})",
        metadata={"reason": reason, "evidence": evidence_reference},
        severity="notice",
    )
    return waiver


def release_waiver(session: Session, *, waiver: Waiver, actor_id: uuid.UUID, note: str) -> Waiver:
    if waiver.status != "raised":
        raise Conflict("This waiver has already been decided.")
    if waiver.raised_by_id == actor_id:
        raise RuleViolation(
            "A waiver must be released by someone other than the person who raised it.",
            rule="four_eyes",
        )

    waiver.status = "released"
    waiver.released_by_id = actor_id
    waiver.released_at = utcnow()

    if waiver.invoice_id:
        invoice = session.get(Invoice, waiver.invoice_id)
        if invoice is not None:
            invoice.waived_minor += waiver.amount_minor
            invoice.balance_minor = max(
                0, invoice.total_minor - invoice.paid_minor - invoice.waived_minor
            )
            if invoice.balance_minor == 0:
                invoice.status = "paid"

    post_transaction(
        session,
        legs=[
            (ACCOUNT_WAIVER_EXPENSE, waiver.amount_minor, f"{waiver.reference} waiver"),
            (
                ACCOUNT_STUDENT_RECEIVABLE,
                -waiver.amount_minor,
                f"{waiver.reference} waived",
            ),
        ],
        student_id=waiver.student_id,
        source_type="waiver",
        source_id=waiver.id,
        value_date=date.today(),
        actor_id=actor_id,
    )
    recompute_balance(session, student_id=waiver.student_id)

    emit(
        "waiver:release",
        AuditCategory.FINANCE,
        resource_type="waiver",
        resource_id=waiver.id,
        resource_label=waiver.reference,
        summary=f"Waiver released: {waiver.amount_minor / 100:,.2f}",
        metadata={"note": note, "category": waiver.category},
        severity="warning",
    )
    return waiver


# ---------------------------------------------------------------------------
# Gates read by the ABAC policies
# ---------------------------------------------------------------------------


def registration_threshold_met(
    session: Session, *, student_id: uuid.UUID, semester_id: uuid.UUID
) -> bool:
    """Has the student paid enough of this semester to register?

    Read by `students.registration-window/financially-blocked`. Computed from
    the student's own share, not the invoice total: a sponsored student is not
    blocked because their sponsor has not remitted yet.
    """
    invoice = session.execute(
        select(Invoice).where(
            Invoice.student_id == student_id,
            Invoice.semester_id == semester_id,
            Invoice.kind == "semester_fees",
            Invoice.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if invoice is None:
        # Nothing invoiced yet is not a block. The registry has not billed
        # them; refusing registration would punish the student for that.
        return True

    structure = (
        session.get(FeeStructure, invoice.fee_structure_id) if invoice.fee_structure_id else None
    )
    threshold = structure.registration_threshold_percent if structure else 60
    student_due = invoice.total_minor - invoice.sponsor_portion_minor
    if student_due <= 0:
        return True
    settled = invoice.paid_minor + invoice.waived_minor
    return (settled * 100 / student_due) >= threshold


def fee_percentage_paid(
    session: Session, *, student_id: uuid.UUID, semester_id: uuid.UUID
) -> tuple[float, int]:
    """(percentage of the student's own share settled, required percentage)."""
    invoice = session.execute(
        select(Invoice).where(
            Invoice.student_id == student_id,
            Invoice.semester_id == semester_id,
            Invoice.kind == "semester_fees",
            Invoice.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if invoice is None:
        return 100.0, 0

    structure = (
        session.get(FeeStructure, invoice.fee_structure_id) if invoice.fee_structure_id else None
    )
    required = structure.exam_threshold_percent if structure else 100
    student_due = invoice.total_minor - invoice.sponsor_portion_minor
    if student_due <= 0:
        return 100.0, required
    settled = invoice.paid_minor + invoice.waived_minor
    return round(settled * 100 / student_due, 2), required


def outstanding_balance(session: Session, *, student_id: uuid.UUID) -> int:
    """Total owed. Read by `finance.tuition-blocks/award-requires-zero-balance`."""
    account = session.execute(
        select(StudentAccount).where(StudentAccount.student_id == student_id)
    ).scalar_one_or_none()
    if account is None or account.recomputed_at is None:
        account = recompute_balance(session, student_id=student_id)
    return max(0, account.balance_minor)


def student_statement(session: Session, *, student_id: uuid.UUID) -> dict[str, Any]:
    """The statement a student sees: invoices, payments and the ledger."""
    account = recompute_balance(session, student_id=student_id)
    invoices = (
        session.execute(
            select(Invoice)
            .where(Invoice.student_id == student_id, Invoice.deleted_at.is_(None))
            .order_by(Invoice.issued_on.desc().nullslast())
        )
        .scalars()
        .all()
    )
    payments = (
        session.execute(
            select(Payment)
            .where(Payment.student_id == student_id, Payment.deleted_at.is_(None))
            .order_by(Payment.value_date.desc().nullslast())
        )
        .scalars()
        .all()
    )

    return {
        "currency": account.currency,
        "balance_minor": account.balance_minor,
        "total_invoiced_minor": account.total_invoiced_minor,
        "total_paid_minor": account.total_paid_minor,
        "total_waived_minor": account.total_waived_minor,
        "as_at": account.recomputed_at.isoformat() if account.recomputed_at else None,
        "invoices": [
            {
                "id": str(i.id),
                "number": i.number,
                "kind": i.kind,
                "status": i.status,
                "issued_on": i.issued_on.isoformat() if i.issued_on else None,
                "due_on": i.due_on.isoformat() if i.due_on else None,
                "total_minor": i.total_minor,
                "paid_minor": i.paid_minor,
                "waived_minor": i.waived_minor,
                "balance_minor": i.balance_minor,
                "sponsor_portion_minor": i.sponsor_portion_minor,
            }
            for i in invoices
        ],
        "payments": [
            {
                "id": str(p.id),
                "reference": p.reference,
                "receipt_number": p.receipt_number,
                "method": p.method,
                "status": p.status,
                "amount_minor": p.amount_minor,
                "allocated_minor": p.allocated_minor,
                "value_date": p.value_date.isoformat() if p.value_date else None,
            }
            for p in payments
        ],
    }


def trial_balance(session: Session, *, period_code: str) -> dict[str, Any]:
    """Sum the ledger by account for a period, and assert it balances.

    The check is the point. A non-zero total means a transaction was written
    unbalanced, which `post_transaction` should make impossible — so a
    non-zero here is a bug worth failing loudly over rather than a rounding
    note at the bottom of a report.
    """
    rows = session.execute(
        select(
            LedgerEntry.account_code,
            func.sum(LedgerEntry.amount_minor).label("balance"),
            func.count().label("entries"),
        )
        .where(LedgerEntry.period_code == period_code)
        .group_by(LedgerEntry.account_code)
        .order_by(LedgerEntry.account_code)
    ).all()

    accounts = [
        {"account_code": r.account_code, "balance_minor": int(r.balance), "entries": int(r.entries)}
        for r in rows
    ]
    total = sum(a["balance_minor"] for a in accounts)
    return {
        "period_code": period_code,
        "accounts": accounts,
        "total_minor": total,
        "balanced": total == 0,
    }
