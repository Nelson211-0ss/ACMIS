"""Life-cycle events: special examinations, cards, transfers, time off.

Kept beside `students.service` rather than inside it because these are the
events that happen *to* a student rather than being part of ordinary study,
and each has the same shape: somebody lodges a request, somebody else decides
it, and the decision has consequences the student cannot reverse.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import date, timedelta
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from acmis.core.audit import AuditCategory, emit
from acmis.core.errors import Conflict, NotFound, RuleViolation
from acmis.core.models import utcnow
from acmis.modules.students.models import (
    ExamCard,
    InstitutionTransfer,
    Registration,
    SpecialExamRequest,
    StatusChange,
    Student,
    StudentIdCard,
)

log = structlog.get_logger(__name__)

#: Grounds that need documentary evidence before a grant. Everything here is
#: verifiable by a third party, which is the point: a special examination
#: rests on the certificate, and without one it is a favour.
EVIDENCE_REQUIRED = frozenset(
    {"illness", "hospitalisation", "bereavement", "accident", "national_duty"}
)

#: A dead semester or dead year. Held here rather than in the model as a
#: constant because the *rules* about how many are permitted live in
#: `assessment.rules`, and this is only the vocabulary.
TIME_OFF_KINDS = frozenset({"dead_semester", "dead_year", "leave_of_absence"})


# ---------------------------------------------------------------------------
# Special and supplementary examinations
# ---------------------------------------------------------------------------


def lodge_special_exam_request(
    session: Session,
    *,
    student: Student,
    course_offering_id: uuid.UUID,
    semester_id: uuid.UUID,
    kind: str,
    ground: str,
    narrative: str,
    missed_on: date | None,
    evidence_attachment_ids: list[uuid.UUID] | None,
    actor_id: uuid.UUID | None,
    fee_minor: int | None = None,
) -> SpecialExamRequest:
    """Lodge an application. Accepted without evidence; not *granted* without it.

    A student in hospital cannot produce a certificate on the day, so the
    application is accepted and the evidence follows. What the deny rule and
    `decide_special_exam` refuse is granting one that never arrived.
    """
    if kind not in ("special", "supplementary"):
        raise RuleViolation(
            "A request is for a special examination (missed with cause) or a "
            "supplementary one (sat and failed).",
            rule="unknown_request_kind",
        )

    existing = (
        session.execute(
            select(SpecialExamRequest).where(
                SpecialExamRequest.student_id == student.id,
                SpecialExamRequest.course_offering_id == course_offering_id,
                SpecialExamRequest.kind == kind,
                SpecialExamRequest.deleted_at.is_(None),
            )
        )
        .scalars()
        .first()
    )
    if existing is not None:
        raise Conflict(
            f"There is already a {kind} examination request for this course "
            f"({existing.reference}, {existing.status})."
        )

    year = date.today().year
    sequence = (
        int(
            session.execute(
                select(func.count()).where(SpecialExamRequest.deleted_at.is_(None))
            ).scalar_one()
        )
        + 1
    )
    request = SpecialExamRequest(
        reference=f"SEX/{year}/{sequence:05d}",
        student_id=student.id,
        course_offering_id=course_offering_id,
        semester_id=semester_id,
        kind=kind,
        ground=ground,
        narrative=narrative,
        missed_on=missed_on,
        evidence_attachment_ids=evidence_attachment_ids or [],
        fee_minor=fee_minor,
        status="submitted",
        submitted_at=utcnow(),
        created_by_id=actor_id,
    )
    session.add(request)
    session.flush()
    emit(
        "special_exam_request:create",
        AuditCategory.ASSESSMENT,
        resource_type="special_exam_request",
        resource_id=request.id,
        resource_label=request.reference,
        summary=f"{kind.capitalize()} examination requested on grounds of {ground}",
        metadata={"ground": ground, "kind": kind},
    )
    return request


def verify_evidence(
    session: Session, *, request: SpecialExamRequest, actor_id: uuid.UUID | None
) -> SpecialExamRequest:
    """Someone has seen the certificate and it is what it claims to be.

    A separate step from lodging, because "a file was uploaded" and "a person
    checked it" are different facts and only the second should support a
    grant.
    """
    if not request.evidence_attachment_ids:
        raise RuleViolation("There is nothing on file to verify.", rule="no_evidence")
    request.evidence_verified_by_id = actor_id
    request.evidence_verified_at = utcnow()
    session.flush()
    emit(
        "special_exam_request:verify_evidence",
        AuditCategory.ASSESSMENT,
        resource_type="special_exam_request",
        resource_id=request.id,
        resource_label=request.reference,
        summary="Evidence checked and accepted",
    )
    return request


def recommend_special_exam(
    session: Session,
    *,
    request: SpecialExamRequest,
    actor_id: uuid.UUID | None,
    note: str | None = None,
) -> SpecialExamRequest:
    """The department's view. Not the decision."""
    if request.status not in ("submitted", "returned"):
        raise Conflict(f"This request is {request.status}.")
    request.status = "recommended"
    request.recommended_by_id = actor_id
    request.recommended_at = utcnow()
    request.decision_note = note
    session.flush()
    emit(
        "special_exam_request:recommend",
        AuditCategory.ASSESSMENT,
        resource_type="special_exam_request",
        resource_id=request.id,
        resource_label=request.reference,
        summary="Recommended by the department",
    )
    return request


def decide_special_exam(
    session: Session,
    *,
    request: SpecialExamRequest,
    grant: bool,
    actor_id: uuid.UUID | None,
    kind: str | None = None,
    note: str | None = None,
    minute_reference: str | None = None,
) -> SpecialExamRequest:
    """The board's decision.

    `kind` lets the board downgrade: a student who asks for a special
    examination having simply not turned up is granted a supplementary at
    best, and the difference is the mark cap. That downgrade is the single
    most consequential thing on this screen, so it is explicit rather than
    inferred.
    """
    if request.status == "mark_recorded":
        raise Conflict(
            "The mark for this request has been recorded. A further sitting is an "
            "appeal, not a special examination."
        )
    final_kind = kind or request.kind
    if grant and final_kind == "special" and request.ground in EVIDENCE_REQUIRED:
        if not request.evidence_attachment_ids:
            raise RuleViolation(
                "A special examination on these grounds cannot be granted without "
                "the evidence on file. The whole difference between a special "
                "examination and a favour is the certificate.",
                rule="evidence_required",
                details={"ground": request.ground},
            )
        if request.evidence_verified_at is None:
            raise RuleViolation(
                "The evidence has not been checked by anyone yet.",
                rule="evidence_unverified",
            )

    request.kind = final_kind
    request.status = "granted" if grant else "refused"
    request.decided_by_id = actor_id
    request.decided_at = utcnow()
    request.decision_note = note
    request.minute_reference = minute_reference
    session.flush()
    emit(
        "special_exam_request:decide",
        AuditCategory.ASSESSMENT,
        resource_type="special_exam_request",
        resource_id=request.id,
        resource_label=request.reference,
        summary=(
            f"{'Granted' if grant else 'Refused'} as a {final_kind} examination"
            + (f" (minute {minute_reference})" if minute_reference else "")
        ),
        severity="notice",
        metadata={"kind": final_kind, "granted": grant},
    )
    return request


def attempt_kind_for(
    session: Session, *, student_id: uuid.UUID, course_offering_id: uuid.UUID
) -> str:
    """`first`, `special` or `supplementary` — which decides the mark cap.

    Read by the marking pipeline through `assessment.rules.cap_mark`. The
    distinction is not cosmetic: a special examination is a first attempt
    taken late and is uncapped, and capping it penalises a student for having
    been in hospital.
    """
    granted = (
        session.execute(
            select(SpecialExamRequest).where(
                SpecialExamRequest.student_id == student_id,
                SpecialExamRequest.course_offering_id == course_offering_id,
                SpecialExamRequest.status.in_(("granted", "scheduled")),
                SpecialExamRequest.deleted_at.is_(None),
            )
        )
        .scalars()
        .first()
    )
    if granted is None:
        return "first"
    return granted.kind


# ---------------------------------------------------------------------------
# Identity cards
# ---------------------------------------------------------------------------


def issue_id_card(
    session: Session,
    *,
    student: Student,
    actor_id: uuid.UUID | None,
    reason: str = "initial",
    campus_id: uuid.UUID | None = None,
    photo_attachment_id: uuid.UUID | None = None,
    expires_on: date | None = None,
    replacement_fee_minor: int | None = None,
) -> StudentIdCard:
    """Issue a card, superseding any live one.

    Supersede rather than edit: an edited card number destroys the trail of
    who held what, and the reason to keep that trail is a card in the wrong
    hands.
    """
    live = (
        session.execute(
            select(StudentIdCard).where(
                StudentIdCard.student_id == student.id,
                StudentIdCard.status == "active",
                StudentIdCard.deleted_at.is_(None),
            )
        )
        .scalars()
        .first()
    )

    serial = f"{student.student_number.replace('/', '')}-{secrets.token_hex(3).upper()}"
    card = StudentIdCard(
        student_id=student.id,
        serial=serial,
        barcode=serial,
        photo_attachment_id=photo_attachment_id,
        campus_id=campus_id,
        issued_on=date.today(),
        expires_on=expires_on,
        reason=reason,
        status="active",
        replacement_fee_minor=replacement_fee_minor,
        supersedes_card_id=live.id if live is not None else None,
        issued_by_id=actor_id,
    )
    session.add(card)
    if live is not None:
        live.status = "superseded"
    session.flush()
    emit(
        "student_id_card:issue",
        AuditCategory.STUDENT_RECORD,
        resource_type="student_id_card",
        resource_id=card.id,
        resource_label=card.serial,
        summary=(
            f"{reason.replace('_', ' ').capitalize()} card issued"
            + (f", superseding {live.serial}" if live is not None else "")
        ),
        metadata={"reason": reason},
    )
    return card


def report_card_lost(
    session: Session,
    *,
    card: StudentIdCard,
    actor_id: uuid.UUID | None,
    stolen: bool = False,
) -> StudentIdCard:
    """Stop a card working. The urgent half of the process.

    Deliberately available to the student themselves: a card in someone
    else's hands opens doors, and making the student wait for an office to
    open is the difference between a nuisance and an incident.
    """
    if card.status not in ("active", "superseded"):
        raise Conflict(f"This card is already {card.status}.")
    card.status = "stolen" if stolen else "lost"
    card.reported_lost_on = date.today()
    session.flush()
    emit(
        "student_id_card:report_lost",
        AuditCategory.STUDENT_RECORD,
        resource_type="student_id_card",
        resource_id=card.id,
        resource_label=card.serial,
        summary=f"Reported {'stolen' if stolen else 'lost'}; card blocked",
        severity="notice",
    )
    return card


def verify_card(session: Session, *, serial_or_barcode: str) -> dict[str, Any]:
    """What a turnstile or a hall door needs, and nothing else.

    Returns whether the card is live and whose it is. Not the student's
    record: a reader at a gate has no business with an address or a fee
    balance, and an endpoint that returns them becomes the way people look
    those up.
    """
    card = (
        session.execute(
            select(StudentIdCard).where(
                (StudentIdCard.serial == serial_or_barcode)
                | (StudentIdCard.barcode == serial_or_barcode),
                StudentIdCard.deleted_at.is_(None),
            )
        )
        .scalars()
        .first()
    )
    if card is None:
        return {"valid": False, "reason": "unknown_card"}

    student = session.get(Student, card.student_id)
    expired = card.expires_on is not None and card.expires_on < date.today()
    valid = card.status == "active" and not expired
    return {
        "valid": valid,
        "reason": None if valid else ("expired" if expired else card.status),
        "serial": card.serial,
        "student_number": student.student_number if student is not None else None,
        "full_name": student.full_name if student is not None else None,
        "student_status": student.status if student is not None else None,
        "photo_attachment_id": str(card.photo_attachment_id) if card.photo_attachment_id else None,
    }


# ---------------------------------------------------------------------------
# Examination cards
# ---------------------------------------------------------------------------


def issue_exam_card(
    session: Session,
    *,
    registration: Registration,
    actor_id: uuid.UUID | None,
    fee_percentage_paid: float,
    required_percentage: float,
    attendance_ok: bool | None,
    session_name: str = "main",
    override_reason: str | None = None,
) -> ExamCard:
    """Issue permission to sit, recording the gates as they stood.

    The gates are stored on the card rather than merely checked, because at
    the hall door the question is not "is this student cleared now" but "was
    this card validly issued, and for which papers" — and a card printed
    before a payment was reversed has to be explainable months later.

    An override is allowed and named. Hardship is real, and a system with no
    override gets one anyway — informally, at the counter, unrecorded.
    """
    if registration.status != "approved":
        raise RuleViolation(
            f"This registration is {registration.status}. A card cannot be issued "
            "against an unapproved registration.",
            rule="registration_not_approved",
        )

    fee_ok = fee_percentage_paid >= required_percentage
    blocked: list[str] = []
    if not fee_ok:
        blocked.append(
            f"fees at {fee_percentage_paid:.0f}% of the {required_percentage:.0f}% required"
        )
    if attendance_ok is False:
        blocked.append("attendance below the threshold")
    if blocked and not override_reason:
        raise RuleViolation(
            "This candidate is not cleared to sit: " + "; ".join(blocked) + ".",
            rule="not_cleared_to_sit",
            details={
                "fee_percentage_paid": fee_percentage_paid,
                "required_percentage": required_percentage,
                "attendance_ok": attendance_ok,
            },
        )

    existing = (
        session.execute(
            select(ExamCard).where(
                ExamCard.registration_id == registration.id,
                ExamCard.session == session_name,
                ExamCard.deleted_at.is_(None),
            )
        )
        .scalars()
        .first()
    )
    if existing is not None and existing.status == "issued":
        raise Conflict(
            f"A {session_name} examination card has already been issued "
            f"({existing.verification_code})."
        )
    if existing is not None:
        existing.status = "superseded"

    # Dropped and withdrawn courses are excluded: a paper the student is no
    # longer taking must not appear on a card already in their hand, and an
    # audited course carries no examination.
    offering_ids = [
        row.course_offering_id
        for row in registration.courses
        if row.deleted_at is None
        and row.dropped_at is None
        and row.withdrawn_at is None
        and not row.is_audit
    ]
    card = ExamCard(
        student_id=registration.student_id,
        registration_id=registration.id,
        semester_id=registration.semester_id,
        # Unguessable rather than sequential: it is verified at the door and
        # by a public endpoint, so a code somebody can construct is a card
        # somebody can forge.
        verification_code=f"EC-{secrets.token_urlsafe(9).upper().replace('_', '')}",
        session=session_name,
        issued_at=utcnow(),
        issued_by_id=actor_id,
        course_offering_ids=offering_ids,
        clearance_snapshot={
            "fee_percentage_paid": fee_percentage_paid,
            "required_percentage": required_percentage,
            "attendance_ok": attendance_ok,
            "overrides": blocked,
        },
        override_reason=override_reason,
        overridden_by_id=actor_id if override_reason else None,
        status="issued",
    )
    session.add(card)
    registration.exam_card_issued_at = utcnow()
    session.flush()
    emit(
        "exam_card:issue",
        AuditCategory.ASSESSMENT,
        resource_type="exam_card",
        resource_id=card.id,
        resource_label=card.verification_code,
        summary=(
            f"Examination card issued for {len(offering_ids)} paper(s)"
            + (f" — override: {override_reason}" if override_reason else "")
        ),
        severity="notice" if override_reason else "info",
        metadata={"session": session_name, "overridden": bool(override_reason)},
    )
    return card


def verify_exam_card(session: Session, *, code: str) -> dict[str, Any]:
    """What an invigilator at the door needs."""
    card = (
        session.execute(
            select(ExamCard).where(
                ExamCard.verification_code == code, ExamCard.deleted_at.is_(None)
            )
        )
        .scalars()
        .first()
    )
    if card is None:
        return {"valid": False, "reason": "unknown_card"}
    student = session.get(Student, card.student_id)
    expired = card.valid_until is not None and card.valid_until < date.today()
    valid = card.status == "issued" and not expired
    return {
        "valid": valid,
        "reason": None if valid else ("expired" if expired else card.status),
        "verification_code": card.verification_code,
        "student_number": student.student_number if student is not None else None,
        "full_name": student.full_name if student is not None else None,
        "session": card.session,
        "papers": [str(offering) for offering in card.course_offering_ids],
        "issued_with_override": bool(card.override_reason),
    }


def revoke_exam_card(
    session: Session, *, card: ExamCard, reason: str, actor_id: uuid.UUID | None
) -> ExamCard:
    """Withdraw permission to sit. A malpractice finding, or a reversed payment."""
    if card.status != "issued":
        raise Conflict(f"This card is already {card.status}.")
    card.status = "revoked"
    card.revoked_at = utcnow()
    card.revoked_reason = reason
    session.flush()
    emit(
        "exam_card:revoke",
        AuditCategory.ASSESSMENT,
        resource_type="exam_card",
        resource_id=card.id,
        resource_label=card.verification_code,
        summary=f"Revoked: {reason}",
        severity="warning",
    )
    return card


# ---------------------------------------------------------------------------
# Time off: dead semesters and dead years
# ---------------------------------------------------------------------------


def time_off_taken(session: Session, *, student_id: uuid.UUID) -> dict[str, int]:
    """How much time off a student has already had.

    Counted from approved status changes rather than from enrolments, because
    a dead year is precisely the absence of an enrolment and cannot be
    counted from one.
    """
    rows = session.execute(
        select(StatusChange.kind, func.count())
        .where(
            StatusChange.student_id == student_id,
            StatusChange.status == "approved",
            StatusChange.kind.in_(tuple(TIME_OFF_KINDS)),
            StatusChange.deleted_at.is_(None),
        )
        .group_by(StatusChange.kind)
    ).all()
    counts = {str(kind): int(total) for kind, total in rows}
    dead_years = counts.get("dead_year", 0)
    dead_semesters = counts.get("dead_semester", 0)
    return {
        "dead_semesters": dead_semesters + dead_years * 2,
        "dead_years": dead_years,
        "leaves_of_absence": counts.get("leave_of_absence", 0),
    }


# ---------------------------------------------------------------------------
# Transfers between institutions
# ---------------------------------------------------------------------------


def lodge_institution_transfer(
    session: Session,
    *,
    direction: str,
    other_institution_name: str,
    actor_id: uuid.UUID | None,
    student_id: uuid.UUID | None = None,
    applicant_id: uuid.UUID | None = None,
    programme_id: uuid.UUID | None = None,
    curriculum_version_id: uuid.UUID | None = None,
    effective_semester_id: uuid.UUID | None = None,
    other_programme_name: str | None = None,
    other_institution_country: str = "UG",
    other_institution_regulator_code: str | None = None,
    credits_claimed: int = 0,
    entry_year_of_study: int | None = None,
    credit_transfer_cap_percent: int | None = None,
    evidence_attachment_ids: list[uuid.UUID] | None = None,
) -> InstitutionTransfer:
    """Open a transfer, in either direction."""
    if direction not in ("incoming", "outgoing"):
        raise RuleViolation("A transfer is incoming or outgoing.", rule="unknown_direction")
    if direction == "incoming" and student_id is None and applicant_id is None:
        raise RuleViolation(
            "An incoming transfer needs the person it is for — an applicant before "
            "admission, a student after it.",
            rule="transfer_subject_required",
        )
    if direction == "outgoing" and student_id is None:
        raise RuleViolation(
            "An outgoing transfer is about a current student.", rule="student_required"
        )

    year = date.today().year
    sequence = (
        int(
            session.execute(
                select(func.count()).where(InstitutionTransfer.deleted_at.is_(None))
            ).scalar_one()
        )
        + 1
    )
    transfer = InstitutionTransfer(
        reference=f"TRF/{year}/{sequence:04d}",
        direction=direction,
        student_id=student_id,
        applicant_id=applicant_id,
        other_institution_name=other_institution_name,
        other_institution_country=other_institution_country,
        other_institution_regulator_code=other_institution_regulator_code,
        other_programme_name=other_programme_name,
        programme_id=programme_id,
        curriculum_version_id=curriculum_version_id,
        effective_semester_id=effective_semester_id,
        entry_year_of_study=entry_year_of_study,
        credits_claimed=credits_claimed,
        credit_transfer_cap_percent=credit_transfer_cap_percent,
        evidence_attachment_ids=evidence_attachment_ids or [],
        status="requested",
        requested_at=utcnow(),
        created_by_id=actor_id,
    )
    session.add(transfer)
    session.flush()
    emit(
        "institution_transfer:create",
        AuditCategory.ADMISSION if direction == "incoming" else AuditCategory.STUDENT_RECORD,
        resource_type="institution_transfer",
        resource_id=transfer.id,
        resource_label=transfer.reference,
        summary=(
            f"{direction.capitalize()} transfer "
            f"{'from' if direction == 'incoming' else 'to'} {other_institution_name}"
        ),
        metadata={"direction": direction, "credits_claimed": credits_claimed},
    )
    return transfer


def assess_transfer_credit(
    session: Session,
    *,
    transfer: InstitutionTransfer,
    assessment: list[dict[str, Any]],
    actor_id: uuid.UUID | None,
    total_programme_credits: int | None = None,
) -> InstitutionTransfer:
    """Record the course-by-course judgement, and check it against the cap.

    The cap is the only thing standing between a transfer scheme and a
    diploma mill: above it the institution is awarding its degree for someone
    else's teaching. It is checked here and copied onto the row, so the
    decision still stands up after the rule changes.
    """
    if transfer.direction != "incoming":
        raise RuleViolation(
            "Only an incoming transfer has credit to assess. An outgoing one "
            "produces a transcript and a letter.",
            rule="not_incoming",
        )
    if transfer.status in ("approved", "rejected"):
        raise Conflict(f"This transfer is already {transfer.status}.")

    awarded = sum(
        int(entry.get("credits_awarded") or 0)
        for entry in assessment
        if entry.get("decision") == "accepted"
    )
    cap_percent = transfer.credit_transfer_cap_percent
    if cap_percent is not None and total_programme_credits:
        ceiling = total_programme_credits * cap_percent // 100
        if awarded > ceiling:
            raise RuleViolation(
                f"{awarded} credits accepted, but the cap for this programme is "
                f"{ceiling} ({cap_percent}% of {total_programme_credits}). Above the "
                "cap the award would rest mostly on another institution's teaching.",
                rule="transfer_cap_exceeded",
                details={
                    "credits_awarded": awarded,
                    "cap_credits": ceiling,
                    "cap_percent": cap_percent,
                },
            )

    transfer.credit_assessment = assessment
    transfer.credits_awarded = awarded
    transfer.status = "assessed"
    transfer.assessed_by_id = actor_id
    transfer.assessed_at = utcnow()
    session.flush()
    emit(
        "institution_transfer:assess",
        AuditCategory.CURRICULUM,
        resource_type="institution_transfer",
        resource_id=transfer.id,
        resource_label=transfer.reference,
        summary=f"{awarded} credit(s) accepted of {transfer.credits_claimed} claimed",
        metadata={"credits_awarded": awarded},
    )
    return transfer


def approve_transfer(
    session: Session,
    *,
    transfer: InstitutionTransfer,
    actor_id: uuid.UUID | None,
    minute_reference: str | None = None,
    note: str | None = None,
) -> InstitutionTransfer:
    """Senate's decision on an assessed transfer."""
    if transfer.direction == "incoming" and transfer.status != "assessed":
        raise Conflict(
            "The credit has not been assessed yet. Approving an unassessed transfer "
            "grants credit nobody has looked at."
        )
    transfer.status = "approved"
    transfer.approved_by_id = actor_id
    transfer.approved_at = utcnow()
    transfer.senate_minute_reference = minute_reference
    transfer.decision_note = note
    session.flush()
    emit(
        "institution_transfer:approve",
        AuditCategory.STUDENT_RECORD,
        resource_type="institution_transfer",
        resource_id=transfer.id,
        resource_label=transfer.reference,
        summary=(
            f"Approved with {transfer.credits_awarded} credit(s) carried"
            + (f" (minute {minute_reference})" if minute_reference else "")
        ),
        severity="notice",
    )
    return transfer


def issue_outgoing_papers(
    session: Session, *, transfer: InstitutionTransfer, actor_id: uuid.UUID | None
) -> InstitutionTransfer:
    """The transcript and the letter of good standing.

    Recorded rather than merely printed, because the commonest query on an
    outgoing transfer a year later is whether the papers were ever sent.
    """
    if transfer.direction != "outgoing":
        raise RuleViolation("Only an outgoing transfer needs papers.", rule="not_outgoing")
    now = utcnow()
    transfer.transcript_issued_at = now
    transfer.letter_issued_at = now
    transfer.status = "completed"
    session.flush()
    emit(
        "institution_transfer:issue_papers",
        AuditCategory.AWARD,
        resource_type="institution_transfer",
        resource_id=transfer.id,
        resource_label=transfer.reference,
        summary="Transcript and letter of good standing issued",
    )
    return transfer


def transfer_state(session: Session, *, transfer_id: uuid.UUID) -> InstitutionTransfer:
    row = session.get(InstitutionTransfer, transfer_id)
    if row is None or row.deleted_at is not None:
        raise NotFound()
    return row


def expire_id_cards(session: Session, *, on: date | None = None) -> int:
    """Mark cards that have passed their expiry. Run daily.

    A card whose printed date has passed but whose status still says active
    is the one a gate lets through.
    """
    today = on or date.today()
    stale = (
        session.execute(
            select(StudentIdCard).where(
                StudentIdCard.status == "active",
                StudentIdCard.expires_on.is_not(None),
                StudentIdCard.expires_on < today,
                StudentIdCard.deleted_at.is_(None),
            )
        )
        .scalars()
        .all()
    )
    for card in stale:
        card.status = "expired"
    session.flush()
    if stale:
        log.info("id_cards_expired", count=len(stale))
    return len(stale)


def graduation_offices(*, has_library: bool = True) -> list[str]:
    """The desks a finalist has to clear.

    The hall is included only where the institution has halls; the rest are
    universal. Ordered as the student walks them, which is how the checklist
    is read.
    """
    offices = ["department", "faculty", "finance"]
    if has_library:
        offices.insert(0, "library")
    return [*offices, "sports", "hall", "registry"]


def next_exam_card_validity(*, semester_ends_on: date | None) -> date | None:
    """A card should die with the examination window, not linger.

    A fortnight past the end of the semester covers a deferred paper without
    leaving a live card in circulation for a year.
    """
    return semester_ends_on + timedelta(days=14) if semester_ends_on else None
