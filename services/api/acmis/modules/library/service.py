"""Library operations: circulation, fines, reservations and stock.

The rules live here rather than in the router because most of them are
arithmetic over the loan policy, and because the desk needs the same answers
from three places — the counter, the self-service kiosk and the nightly job.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

import structlog
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from acmis.core.audit import AuditCategory, emit
from acmis.core.errors import Conflict, NotFound, RuleViolation
from acmis.core.models import utcnow
from acmis.modules.library.models import (
    CatalogueCopy,
    CatalogueRecord,
    CopyStatus,
    LibraryFine,
    LibraryMember,
    Loan,
    LoanPolicy,
    LoanStatus,
    Reservation,
)

log = structlog.get_logger(__name__)

#: How long a copy is held at the desk once a reservation comes up. Short on
#: purpose: a reader who has waited three weeks for a book is not helped by
#: the next one sitting uncollected for a fortnight.
HOLD_SHELF_DAYS = 5

#: Statuses that mean the copy is not on the shelf to be lent.
UNAVAILABLE = frozenset(
    {
        CopyStatus.ON_LOAN,
        CopyStatus.LOST,
        CopyStatus.MISSING,
        CopyStatus.WITHDRAWN,
        CopyStatus.BINDING,
        CopyStatus.IN_TRANSIT,
    }
)


# ---------------------------------------------------------------------------
# Membership
# ---------------------------------------------------------------------------


def category_for_student(*, award_level: str | None) -> str:
    """Which loan policy a student falls under.

    Postgraduates borrow more, for longer: their reading is deeper and their
    programmes are shorter, so the same allowance would have them queueing
    for a book they need for six weeks.
    """
    level = (award_level or "").lower()
    if any(word in level for word in ("master", "doctor", "phd", "postgraduate")):
        return "postgraduate"
    return "undergraduate"


def ensure_member(
    session: Session,
    *,
    student_id: uuid.UUID | None = None,
    staff_id: uuid.UUID | None = None,
    borrower_category: str = "undergraduate",
    membership_number: str | None = None,
    home_library_id: uuid.UUID | None = None,
    expires_on: date | None = None,
) -> LibraryMember:
    """Find or create the membership for a person. Idempotent.

    Created on first use rather than in bulk at enrolment, because a
    membership for every student whether or not they ever borrow is a
    membership list nobody can use to find the readers.
    """
    if student_id is None and staff_id is None:
        raise RuleViolation(
            "A membership needs a student or a member of staff.", rule="member_identity"
        )
    stmt = select(LibraryMember).where(LibraryMember.deleted_at.is_(None))
    stmt = stmt.where(
        LibraryMember.student_id == student_id
        if student_id is not None
        else LibraryMember.staff_id == staff_id
    )
    existing = session.execute(stmt).scalars().first()
    if existing is not None:
        return existing

    member = LibraryMember(
        membership_number=membership_number or f"LIB/{uuid.uuid4().hex[:8].upper()}",
        student_id=student_id,
        staff_id=staff_id,
        borrower_category=borrower_category,
        home_library_id=home_library_id,
        joined_on=date.today(),
        expires_on=expires_on,
        status="active",
    )
    session.add(member)
    session.flush()
    emit(
        "library_member:create",
        AuditCategory.LIBRARY,
        resource_type="library_member",
        resource_id=member.id,
        resource_label=member.membership_number,
        summary="Library membership created",
    )
    return member


def recompute_member(session: Session, *, member: LibraryMember) -> LibraryMember:
    """Refresh the cached counters the desk reads on every issue.

    Cached because the desk needs a yes/no in the time it takes to scan a
    card, and summing open fines per issue is the query that makes a busy
    desk slow. Recomputed rather than incremented: a counter that drifts is
    worse than one that costs a query, because the desk stops believing it.
    """
    member.outstanding_fines_minor = int(
        session.execute(
            select(func.coalesce(func.sum(LibraryFine.amount_minor), 0)).where(
                LibraryFine.member_id == member.id,
                LibraryFine.status.in_(("raised", "invoiced")),
                LibraryFine.deleted_at.is_(None),
            )
        ).scalar_one()
    )
    member.items_on_loan = int(
        session.execute(
            select(func.count()).where(
                Loan.member_id == member.id,
                Loan.status.in_((LoanStatus.OPEN, LoanStatus.OVERDUE)),
                Loan.deleted_at.is_(None),
            )
        ).scalar_one()
    )
    member.fines_recomputed_at = utcnow()
    session.flush()
    return member


# ---------------------------------------------------------------------------
# Loan policy
# ---------------------------------------------------------------------------


def policy_for(
    session: Session, *, member: LibraryMember, loan_class: str, library_id: uuid.UUID
) -> LoanPolicy:
    """The rule that governs this reader borrowing this class of stock.

    Resolved most-specific-first: a policy for this branch beats the
    institution-wide one, because a law library that lends for three days
    cannot be described by a rule written for the main library.
    """
    stmt = (
        select(LoanPolicy)
        .where(
            LoanPolicy.borrower_category == member.borrower_category,
            LoanPolicy.loan_class == loan_class,
            LoanPolicy.is_active.is_(True),
            LoanPolicy.deleted_at.is_(None),
            # Not `library_id IN (:id, NULL)`: nothing is ever `IN` a NULL in
            # SQL, so the institution-wide policy would silently never match
            # and a branch with no policy of its own would refuse every issue.
            or_(LoanPolicy.library_id == library_id, LoanPolicy.library_id.is_(None)),
        )
        # `NULLS LAST` puts the branch-specific rule first.
        .order_by(LoanPolicy.library_id.desc().nullslast())
    )
    policy = session.execute(stmt).scalars().first()
    if policy is None:
        raise RuleViolation(
            f"No loan policy for a {member.borrower_category} borrowing "
            f"{loan_class} stock. Add one before issuing.",
            rule="no_loan_policy",
            details={"borrower_category": member.borrower_category, "loan_class": loan_class},
        )
    return policy


def check_can_borrow(
    session: Session, *, member: LibraryMember, copy: CatalogueCopy, policy: LoanPolicy
) -> None:
    """Everything that stops an issue, checked in the order the desk cares.

    Ordered deliberately: the reasons a reader is turned away are reported
    one at a time, and the first one reported should be the one they can do
    something about. "You owe 40,000" is actionable; "this copy is reference
    only" is not.
    """
    if member.status != "active":
        raise RuleViolation(f"This membership is {member.status}.", rule="member_not_active")
    if member.expires_on is not None and member.expires_on < date.today():
        raise RuleViolation("This membership expired.", rule="member_expired")

    block = policy.borrowing_block_debt_minor
    if block is not None and member.outstanding_fines_minor >= block:
        raise RuleViolation(
            "There are fines outstanding on this membership.",
            rule="fines_outstanding",
            details={
                "outstanding_minor": member.outstanding_fines_minor,
                "limit_minor": block,
            },
        )
    if member.items_on_loan >= policy.max_copies:
        raise RuleViolation(
            f"This reader already has {member.items_on_loan} items out; the limit is "
            f"{policy.max_copies}.",
            rule="loan_limit_reached",
        )
    if copy.loan_class == "reference" or copy.status == CopyStatus.REFERENCE_ONLY:
        raise RuleViolation(
            "Reference stock does not leave the reading room.", rule="reference_only"
        )
    if copy.status in UNAVAILABLE:
        raise Conflict(f"This copy is {copy.status.replace('_', ' ')}.")

    # A copy on the hold shelf belongs to the reader whose reservation came
    # up, not to whoever reaches the desk with it first.
    if copy.status == CopyStatus.ON_HOLD_SHELF:
        held = (
            session.execute(
                select(Reservation).where(
                    Reservation.allocated_copy_id == copy.id,
                    Reservation.status == "ready",
                    Reservation.deleted_at.is_(None),
                )
            )
            .scalars()
            .first()
        )
        if held is not None and held.member_id != member.id:
            raise Conflict("This copy is being held for another reader.")


# ---------------------------------------------------------------------------
# Circulation
# ---------------------------------------------------------------------------


def issue(
    session: Session,
    *,
    copy: CatalogueCopy,
    member: LibraryMember,
    actor_id: uuid.UUID | None,
    due_on: date | None = None,
) -> Loan:
    """Issue one copy to one reader."""
    recompute_member(session, member=member)
    policy = policy_for(
        session, member=member, loan_class=copy.loan_class, library_id=copy.library_id
    )
    check_can_borrow(session, member=member, copy=copy, policy=policy)

    # An explicit date is honoured — a librarian shortening a loan before a
    # vacation is normal — but never lengthened beyond the policy, which is
    # the one thing the policy exists to fix.
    computed = date.today() + timedelta(days=policy.loan_days)
    final_due = min(due_on, computed) if due_on is not None else computed

    loan = Loan(
        copy_id=copy.id,
        member_id=member.id,
        library_id=copy.library_id,
        issued_at=utcnow(),
        issued_by_id=actor_id,
        due_on=final_due,
        original_due_on=final_due,
        status=LoanStatus.OPEN,
        fine_per_day_minor=policy.fine_per_day_minor,
    )
    session.add(loan)
    copy.status = CopyStatus.ON_LOAN
    copy.times_issued += 1
    copy.last_seen_on = date.today()
    session.flush()
    recompute_member(session, member=member)

    # Satisfying the reader's own reservation, if this issue is what it was
    # waiting for.
    reservation = (
        session.execute(
            select(Reservation).where(
                Reservation.record_id == copy.record_id,
                Reservation.member_id == member.id,
                Reservation.status.in_(("ready", "waiting")),
                Reservation.deleted_at.is_(None),
            )
        )
        .scalars()
        .first()
    )
    if reservation is not None:
        reservation.status = "collected"
        reservation.collected_at = utcnow()
        session.flush()
        _renumber_queue(session, record_id=copy.record_id)

    emit(
        "library_loan:issue",
        AuditCategory.LIBRARY,
        resource_type="library_loan",
        resource_id=loan.id,
        resource_label=f"copy {copy.accession_number}",
        summary=f"Issued to {member.membership_number}, due {final_due:%d %b %Y}",
        metadata={"due_on": final_due.isoformat(), "accession": copy.accession_number},
    )
    return loan


def overdue_fine_for(loan: Loan, *, policy: LoanPolicy | None, on: date) -> tuple[int, int]:
    """`(days charged, amount)` for a loan returned or standing on `on`.

    The grace period is subtracted from the chargeable days rather than used
    as a threshold: a reader three days late with a two-day grace is charged
    for one day, not three. Charging from day one the moment grace lapses is
    the arithmetic readers dispute, and they are right to.
    """
    rate = loan.fine_per_day_minor
    grace = policy.grace_days if policy is not None else 0
    cap = policy.fine_cap_minor if policy is not None else None
    if rate <= 0 or on <= loan.due_on:
        return 0, 0
    days = (on - loan.due_on).days - grace
    if days <= 0:
        return 0, 0
    amount = days * rate
    if cap is not None:
        amount = min(amount, cap)
    return days, amount


def receive(
    session: Session,
    *,
    loan: Loan,
    actor_id: uuid.UUID | None,
    condition: str | None = None,
    on: date | None = None,
) -> Loan:
    """Take a copy back in.

    The loan row is closed by stamping it, never edited into a different
    shape: the history of who held what is the only evidence in a dispute
    about a missing book.
    """
    if loan.status not in (LoanStatus.OPEN, LoanStatus.OVERDUE):
        raise Conflict(f"This loan is already {loan.status}.")
    received_on = on or date.today()
    copy = session.get(CatalogueCopy, loan.copy_id)
    member = session.get(LibraryMember, loan.member_id)
    if copy is None or member is None:  # pragma: no cover - referential integrity
        raise NotFound()

    policy = None
    try:
        policy = policy_for(
            session, member=member, loan_class=copy.loan_class, library_id=loan.library_id
        )
    except RuleViolation:
        # A policy withdrawn since the issue must not stop a return. The rate
        # on the loan row is what the reader was told, and it is enough.
        policy = None

    loan.returned_on = received_on
    loan.returned_at = utcnow()
    loan.received_by_id = actor_id
    loan.status = LoanStatus.RETURNED
    loan.return_condition = condition
    copy.last_seen_on = received_on
    if condition:
        copy.condition = condition
    session.flush()

    days, amount = overdue_fine_for(loan, policy=policy, on=received_on)
    if amount > 0:
        raise_fine(
            session,
            member=member,
            loan=loan,
            reason="overdue",
            amount_minor=amount,
            actor_id=actor_id,
            days_overdue=days,
            rate_per_day_minor=loan.fine_per_day_minor,
        )

    # The next reader in the queue, if any; otherwise back on the shelf.
    allocated = allocate_next_reservation(session, copy=copy)
    if not allocated:
        copy.status = CopyStatus.AVAILABLE
    session.flush()
    recompute_member(session, member=member)

    emit(
        "library_loan:return",
        AuditCategory.LIBRARY,
        resource_type="library_loan",
        resource_id=loan.id,
        resource_label=f"copy {copy.accession_number}",
        summary=(
            f"Returned {received_on:%d %b %Y}"
            + (f"; {days} day(s) overdue" if days else "")
            + ("; held for the next reader" if allocated else "")
        ),
    )
    return loan


def renew(session: Session, *, loan: Loan, actor_id: uuid.UUID | None) -> Loan:
    """Extend a loan, unless someone is waiting.

    A queue beats a renewal. The reader with the book has had it for the full
    period; the one waiting has had nothing.
    """
    if loan.status not in (LoanStatus.OPEN, LoanStatus.OVERDUE):
        raise Conflict(f"This loan is {loan.status} and cannot be renewed.")
    copy = session.get(CatalogueCopy, loan.copy_id)
    member = session.get(LibraryMember, loan.member_id)
    if copy is None or member is None:  # pragma: no cover
        raise NotFound()

    policy = policy_for(
        session, member=member, loan_class=copy.loan_class, library_id=loan.library_id
    )
    if loan.renewals >= policy.max_renewals:
        raise RuleViolation(
            f"This loan has been renewed {loan.renewals} time(s); "
            f"{policy.max_renewals} are allowed.",
            rule="renewal_limit",
        )
    waiting = session.execute(
        select(func.count()).where(
            Reservation.record_id == copy.record_id,
            Reservation.status == "waiting",
            Reservation.deleted_at.is_(None),
        )
    ).scalar_one()
    if waiting:
        raise RuleViolation(
            f"{waiting} reader(s) are waiting for this title, so it cannot be renewed.",
            rule="reserved_by_another",
        )
    recompute_member(session, member=member)
    block = policy.borrowing_block_debt_minor
    if block is not None and member.outstanding_fines_minor >= block:
        raise RuleViolation(
            "There are fines outstanding on this membership.", rule="fines_outstanding"
        )

    # Renewed from today, not from the old due date: renewing a fortnight
    # late would otherwise grant a loan that has already expired.
    loan.due_on = date.today() + timedelta(days=policy.loan_days)
    loan.renewals += 1
    loan.status = LoanStatus.OPEN
    session.flush()
    emit(
        "library_loan:renew",
        AuditCategory.LIBRARY,
        resource_type="library_loan",
        resource_id=loan.id,
        summary=f"Renewed to {loan.due_on:%d %b %Y} (renewal {loan.renewals})",
    )
    return loan


def declare_lost(
    session: Session,
    *,
    loan: Loan,
    actor_id: uuid.UUID | None,
    replacement_minor: int | None = None,
) -> LibraryFine:
    """Write a copy off and charge for it.

    Charged at the recorded price where there is one, because a replacement
    charge based on a guess is a charge that gets waived. The processing fee
    is separate and small, and it is what stops "lost" being cheaper than
    returning a book late.
    """
    copy = session.get(CatalogueCopy, loan.copy_id)
    member = session.get(LibraryMember, loan.member_id)
    if copy is None or member is None:  # pragma: no cover
        raise NotFound()

    amount = replacement_minor if replacement_minor is not None else (copy.price_minor or 0)
    if amount <= 0:
        raise RuleViolation(
            "This copy has no recorded price, so the replacement charge has to be stated.",
            rule="no_replacement_price",
        )
    loan.status = LoanStatus.LOST
    copy.status = CopyStatus.LOST
    session.flush()
    fine = raise_fine(
        session,
        member=member,
        loan=loan,
        reason="loss",
        amount_minor=amount,
        actor_id=actor_id,
        copy_id=copy.id,
    )
    emit(
        "library_loan:declare_lost",
        AuditCategory.LIBRARY,
        resource_type="library_loan",
        resource_id=loan.id,
        resource_label=f"copy {copy.accession_number}",
        summary=f"Declared lost; charged {amount / 100:,.0f}",
        severity="notice",
    )
    return fine


# ---------------------------------------------------------------------------
# Reservations
# ---------------------------------------------------------------------------


def reserve(session: Session, *, record: CatalogueRecord, member: LibraryMember) -> Reservation:
    """Queue a reader for a work.

    Against the record, not a copy: the reader wants the book, and whichever
    copy comes back first satisfies them.
    """
    if member.status != "active":
        raise RuleViolation(f"This membership is {member.status}.", rule="member_not_active")

    existing = (
        session.execute(
            select(Reservation).where(
                Reservation.record_id == record.id,
                Reservation.member_id == member.id,
                Reservation.status.in_(("waiting", "ready")),
                Reservation.deleted_at.is_(None),
            )
        )
        .scalars()
        .first()
    )
    if existing is not None:
        return existing

    # A copy sitting on the shelf makes a reservation pointless, and the
    # honest answer is more useful than a queue of one.
    available = session.execute(
        select(func.count()).where(
            CatalogueCopy.record_id == record.id,
            CatalogueCopy.status == CopyStatus.AVAILABLE,
            CatalogueCopy.deleted_at.is_(None),
        )
    ).scalar_one()
    if available:
        raise RuleViolation("A copy of this title is on the shelf now.", rule="copy_available")

    position = (
        int(
            session.execute(
                select(func.count()).where(
                    Reservation.record_id == record.id,
                    Reservation.status == "waiting",
                    Reservation.deleted_at.is_(None),
                )
            ).scalar_one()
        )
        + 1
    )
    reservation = Reservation(
        record_id=record.id,
        member_id=member.id,
        library_id=member.home_library_id,
        requested_at=utcnow(),
        queue_position=position,
        status="waiting",
    )
    session.add(reservation)
    session.flush()
    emit(
        "library_reservation:create",
        AuditCategory.LIBRARY,
        resource_type="library_reservation",
        resource_id=reservation.id,
        resource_label=record.title,
        summary=f"Reserved; position {position} in the queue",
    )
    return reservation


def allocate_next_reservation(session: Session, *, copy: CatalogueCopy) -> bool:
    """Put a returned copy aside for the reader at the head of the queue."""
    next_up = (
        session.execute(
            select(Reservation)
            .where(
                Reservation.record_id == copy.record_id,
                Reservation.status == "waiting",
                Reservation.deleted_at.is_(None),
            )
            .order_by(Reservation.queue_position, Reservation.requested_at)
        )
        .scalars()
        .first()
    )
    if next_up is None:
        return False

    next_up.status = "ready"
    next_up.allocated_copy_id = copy.id
    next_up.allocated_at = utcnow()
    next_up.collect_by = date.today() + timedelta(days=HOLD_SHELF_DAYS)
    copy.status = CopyStatus.ON_HOLD_SHELF
    session.flush()
    _renumber_queue(session, record_id=copy.record_id)
    emit(
        "library_reservation:allocate",
        AuditCategory.LIBRARY,
        resource_type="library_reservation",
        resource_id=next_up.id,
        summary=f"Copy held until {next_up.collect_by:%d %b %Y}",
    )
    return True


def expire_hold_shelf(session: Session, *, on: date | None = None) -> int:
    """Release copies nobody collected. Run daily.

    An uncollected hold is worse than no hold: the copy is off the shelf, the
    reader who wanted it has gone elsewhere, and the next in the queue is
    still waiting.
    """
    today = on or date.today()
    stale = (
        session.execute(
            select(Reservation).where(
                Reservation.status == "ready",
                Reservation.collect_by < today,
                Reservation.deleted_at.is_(None),
            )
        )
        .scalars()
        .all()
    )
    released = 0
    for reservation in stale:
        reservation.status = "expired"
        copy = (
            session.get(CatalogueCopy, reservation.allocated_copy_id)
            if reservation.allocated_copy_id
            else None
        )
        session.flush()
        if (
            copy is not None
            and copy.status == CopyStatus.ON_HOLD_SHELF
            and not allocate_next_reservation(session, copy=copy)
        ):
            copy.status = CopyStatus.AVAILABLE
        released += 1
    if released:
        session.flush()
        log.info("hold_shelf_expired", released=released)
    return released


def _renumber_queue(session: Session, *, record_id: uuid.UUID) -> None:
    """Close the gaps after a queue changes.

    Recomputed rather than left gap-filled, because a queue with holes in it
    cannot be explained to the person standing at the desk.
    """
    waiting = (
        session.execute(
            select(Reservation)
            .where(
                Reservation.record_id == record_id,
                Reservation.status == "waiting",
                Reservation.deleted_at.is_(None),
            )
            .order_by(Reservation.queue_position, Reservation.requested_at)
        )
        .scalars()
        .all()
    )
    for index, reservation in enumerate(waiting, start=1):
        reservation.queue_position = index
    session.flush()


# ---------------------------------------------------------------------------
# Fines
# ---------------------------------------------------------------------------


def raise_fine(
    session: Session,
    *,
    member: LibraryMember,
    reason: str,
    amount_minor: int,
    actor_id: uuid.UUID | None,
    loan: Loan | None = None,
    copy_id: uuid.UUID | None = None,
    days_overdue: int | None = None,
    rate_per_day_minor: int | None = None,
    note: str | None = None,
) -> LibraryFine:
    """Record money owed. Settled through finance, never here."""
    fine = LibraryFine(
        member_id=member.id,
        loan_id=loan.id if loan is not None else None,
        copy_id=copy_id or (loan.copy_id if loan is not None else None),
        reason=reason,
        amount_minor=amount_minor,
        days_overdue=days_overdue,
        rate_per_day_minor=rate_per_day_minor,
        status="raised",
        raised_on=date.today(),
        raised_by_id=actor_id,
        note=note,
    )
    session.add(fine)
    session.flush()
    recompute_member(session, member=member)
    emit(
        "library_fine:create",
        AuditCategory.LIBRARY,
        resource_type="library_fine",
        resource_id=fine.id,
        summary=(
            f"{reason.replace('_', ' ').capitalize()} charge of {amount_minor / 100:,.0f}"
            + (
                f" ({days_overdue} day(s) at {(rate_per_day_minor or 0) / 100:,.0f})"
                if days_overdue
                else ""
            )
        ),
        metadata={"reason": reason, "amount_minor": amount_minor},
    )
    return fine


def waive_fine(
    session: Session, *, fine: LibraryFine, actor_id: uuid.UUID | None, reason: str
) -> LibraryFine:
    """Forgive a charge, with a reason on the record.

    Money the institution has decided not to collect, so it needs the same
    treatment as a fee waiver: a stated reason and a name.
    """
    if fine.status in ("waived", "written_off"):
        raise Conflict("This charge has already been waived.")
    if fine.status == "paid":
        raise Conflict("This charge has been paid; a refund is a finance matter.")
    fine.status = "waived"
    fine.waived_by_id = actor_id
    fine.waiver_reason = reason
    fine.settled_on = date.today()
    session.flush()
    member = session.get(LibraryMember, fine.member_id)
    if member is not None:
        recompute_member(session, member=member)
    emit(
        "library_fine:waive",
        AuditCategory.LIBRARY,
        resource_type="library_fine",
        resource_id=fine.id,
        summary=f"Waived {fine.amount_minor / 100:,.0f}: {reason}",
        severity="notice",
        metadata={"reason": reason},
    )
    return fine


def accrue_overdue(session: Session, *, on: date | None = None) -> dict[str, int]:
    """Mark overdue loans and charge what they have accrued. Run daily.

    Charges the *difference* rather than raising a fresh fine each night: a
    reader thirty days late owes one thirty-day charge, not thirty charges.
    The distinction is invisible in the total and very visible on a statement.
    """
    today = on or date.today()
    open_loans = (
        session.execute(
            select(Loan).where(
                Loan.status.in_((LoanStatus.OPEN, LoanStatus.OVERDUE)),
                Loan.due_on < today,
                Loan.deleted_at.is_(None),
            )
        )
        .scalars()
        .all()
    )

    marked = 0
    charged = 0
    total = 0
    for loan in open_loans:
        if loan.status != LoanStatus.OVERDUE:
            loan.status = LoanStatus.OVERDUE
            marked += 1
        member = session.get(LibraryMember, loan.member_id)
        copy = session.get(CatalogueCopy, loan.copy_id)
        if member is None or copy is None:  # pragma: no cover
            continue
        policy = None
        try:
            policy = policy_for(
                session,
                member=member,
                loan_class=copy.loan_class,
                library_id=loan.library_id,
            )
        except RuleViolation:
            policy = None
        days, amount = overdue_fine_for(loan, policy=policy, on=today)
        if amount <= 0:
            continue

        already = int(
            session.execute(
                select(func.coalesce(func.sum(LibraryFine.amount_minor), 0)).where(
                    LibraryFine.loan_id == loan.id,
                    LibraryFine.reason == "overdue",
                    LibraryFine.status.in_(("raised", "invoiced", "paid")),
                    LibraryFine.deleted_at.is_(None),
                )
            ).scalar_one()
        )
        outstanding = amount - already
        if outstanding <= 0:
            continue
        raise_fine(
            session,
            member=member,
            loan=loan,
            reason="overdue",
            amount_minor=outstanding,
            actor_id=None,
            days_overdue=days,
            rate_per_day_minor=loan.fine_per_day_minor,
            note="Accrued by the nightly overdue run.",
        )
        charged += 1
        total += outstanding

    session.flush()
    log.info("overdue_accrued", marked=marked, charged=charged, total_minor=total)
    return {"marked_overdue": marked, "fines_raised": charged, "total_minor": total}


# ---------------------------------------------------------------------------
# Clearance
# ---------------------------------------------------------------------------


def clearance_state(session: Session, *, student_id: uuid.UUID) -> dict[str, Any]:
    """What the library is owed by a leaving student.

    The answer graduation clearance needs, and shaped so the student can act
    on it: not "blocked" but which books and how much.
    """
    member = (
        session.execute(
            select(LibraryMember).where(
                LibraryMember.student_id == student_id, LibraryMember.deleted_at.is_(None)
            )
        )
        .scalars()
        .first()
    )
    if member is None:
        return {"member": None, "clear": True, "items_out": 0, "outstanding_minor": 0}

    recompute_member(session, member=member)
    outstanding_loans = session.execute(
        select(Loan, CatalogueCopy, CatalogueRecord)
        .join(CatalogueCopy, CatalogueCopy.id == Loan.copy_id)
        .join(CatalogueRecord, CatalogueRecord.id == CatalogueCopy.record_id)
        .where(
            Loan.member_id == member.id,
            Loan.status.in_((LoanStatus.OPEN, LoanStatus.OVERDUE)),
            Loan.deleted_at.is_(None),
        )
    ).all()
    return {
        "member": {
            "id": str(member.id),
            "membership_number": member.membership_number,
            "status": member.status,
        },
        "clear": member.items_on_loan == 0 and member.outstanding_fines_minor == 0,
        "items_out": member.items_on_loan,
        "outstanding_minor": member.outstanding_fines_minor,
        "items": [
            {
                "loan_id": str(loan.id),
                "title": record.title,
                "accession_number": copy.accession_number,
                "due_on": loan.due_on.isoformat(),
                "overdue": loan.due_on < date.today(),
            }
            for loan, copy, record in outstanding_loans
        ],
    }
