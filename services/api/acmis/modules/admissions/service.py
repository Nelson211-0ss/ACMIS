"""Admissions domain logic: eligibility, scoring, selection, enrolment."""

from __future__ import annotations

import secrets
import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from acmis.core.abac import bulk_decide
from acmis.core.abac.enforcement import decide
from acmis.core.audit import AuditCategory, diff, emit
from acmis.core.errors import Conflict, NotFound, RuleViolation, ValidationFailed
from acmis.core.models import utcnow
from acmis.core.schemas import Capability
from acmis.modules.admissions.models import (
    AdmissionScheme,
    Applicant,
    Application,
    ApplicationChoice,
    ApplicationEvent,
    ApplicationStatus,
    Offer,
    ProgrammeIntake,
    Qualification,
    SchemeStatus,
    SelectionList,
)

log = structlog.get_logger(__name__)

APPLICATION_ACTIONS = (
    "application:read",
    "application:update",
    "application:submit",
    "application:score",
    "application:recommend",
    "application:read_sensitive",
    "offer:issue",
)


def capabilities_for(ctx: Any, application: Application) -> list[Capability]:
    allowed = bulk_decide(
        engine=ctx.engine,
        actions=APPLICATION_ACTIONS,
        resource_type="application",
        resource=application,
    )
    return [Capability(action=a, allowed=v) for a, v in allowed.items()]


# ---------------------------------------------------------------------------
# Application lifecycle
# ---------------------------------------------------------------------------


def next_application_number(session: Session, scheme: AdmissionScheme) -> str:
    """`APP/UG-2026/000142`.

    Sequential within a scheme because applicants and counter staff quote
    these to each other over the phone, and a UUID is unusable for that. The
    count-based derivation is safe under the unique constraint: a collision
    fails the insert rather than producing a duplicate, and the retry picks the
    next number.
    """
    used = session.execute(
        select(func.count()).select_from(Application).where(Application.scheme_id == scheme.id)
    ).scalar_one()
    return f"APP/{scheme.code}/{used + 1:06d}"


def start_application(
    session: Session,
    *,
    applicant_id: uuid.UUID | None,
    scheme_id: uuid.UUID,
    programme_intake_ids: list[uuid.UUID],
    actor_id: uuid.UUID,
) -> Application:
    if applicant_id is None:
        raise ValidationFailed("This account is not linked to an applicant record.")

    scheme = session.get(AdmissionScheme, scheme_id)
    if scheme is None or scheme.deleted_at is not None:
        raise NotFound("That admission scheme does not exist.")

    now = utcnow()
    if scheme.status != SchemeStatus.OPEN:
        raise RuleViolation("This scheme is not open for applications.", rule="scheme_not_open")
    deadline = scheme.late_closes_at or scheme.closes_at
    if now > deadline:
        raise RuleViolation(f"Applications closed on {deadline:%d %B %Y}.", rule="scheme_closed")

    existing = session.execute(
        select(Application).where(
            Application.applicant_id == applicant_id,
            Application.scheme_id == scheme_id,
            Application.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if existing is not None:
        # Returning the existing draft rather than erroring. An applicant who
        # taps "Apply" twice on a slow connection should land back on their own
        # form, not on an error page.
        if existing.status == ApplicationStatus.DRAFT:
            return existing
        raise Conflict("You have already applied under this scheme.")

    if len(programme_intake_ids) > scheme.max_programme_choices:
        raise RuleViolation(
            f"This scheme allows at most {scheme.max_programme_choices} programme choices.",
            rule="too_many_choices",
        )
    if len(set(programme_intake_ids)) != len(programme_intake_ids):
        raise ValidationFailed("Each programme may only be chosen once.")

    application = Application(
        number=next_application_number(session, scheme),
        applicant_id=applicant_id,
        scheme_id=scheme_id,
        status=ApplicationStatus.DRAFT,
        is_late=now > scheme.closes_at,
        created_by_id=actor_id,
    )
    session.add(application)
    session.flush()
    _set_choices(session, application, programme_intake_ids)

    _record_event(
        session,
        application,
        kind="created",
        message="Application started.",
        to_status=ApplicationStatus.DRAFT,
        actor_id=actor_id,
    )
    emit(
        "application:create",
        AuditCategory.ADMISSION,
        resource_type="application",
        resource_id=application.id,
        resource_label=application.number,
        summary=f"Application {application.number} started under {scheme.code}",
    )
    return application


def _set_choices(session: Session, application: Application, intake_ids: list[uuid.UUID]) -> None:
    """Replace the ranked choices, and denormalise the faculties they touch.

    `faculty_ids` on the application is what the faculty-review policy reads,
    so it has to be rebuilt whenever the choices change — a stale value is a
    dean who can still see an application that no longer ranks their faculty,
    or cannot see one that now does.
    """
    for existing in list(application.choices):
        session.delete(existing)
    session.flush()

    faculties: set[uuid.UUID] = set()
    for rank, intake_id in enumerate(intake_ids, start=1):
        intake = session.get(ProgrammeIntake, intake_id)
        if intake is None or intake.deleted_at is not None:
            raise ValidationFailed(f"Programme choice {rank} is not available.")
        if intake.scheme_id != application.scheme_id:
            raise ValidationFailed(
                f"Programme choice {rank} does not belong to this admission scheme."
            )
        session.add(
            ApplicationChoice(
                application_id=application.id, programme_intake_id=intake_id, rank=rank
            )
        )
        programme = getattr(intake, "programme", None)
        if programme is None:
            from acmis.modules.curriculum.models import Programme

            programme = session.get(Programme, intake.programme_id)
        if programme is not None:
            faculties.update(programme.faculty_ids or ())

    application.faculty_ids = sorted(faculties)
    session.flush()


def update_application(
    session: Session, *, application: Application, changes: dict[str, Any], actor_id: uuid.UUID
) -> Application:
    before = {
        "status": application.status,
        "review_notes": application.review_notes,
        "flags": list(application.flags),
        "choices": [str(c.programme_intake_id) for c in application.choices],
    }

    if "programme_intake_ids" in changes and changes["programme_intake_ids"] is not None:
        if application.status != ApplicationStatus.DRAFT:
            raise Conflict("Programme choices cannot be changed after submission.")
        _set_choices(session, application, list(changes["programme_intake_ids"]))
    if "review_notes" in changes:
        application.review_notes = changes["review_notes"]
    if "flags" in changes and changes["flags"] is not None:
        application.flags = list(changes["flags"])

    application.updated_by_id = actor_id
    session.flush()

    after = {
        "status": application.status,
        "review_notes": application.review_notes,
        "flags": list(application.flags),
        "choices": [str(c.programme_intake_id) for c in application.choices],
    }
    emit(
        "application:update",
        AuditCategory.ADMISSION,
        resource_type="application",
        resource_id=application.id,
        resource_label=application.number,
        summary="Application updated",
        changes=diff(before, after),
    )
    return application


def check_eligibility(session: Session, *, application: Application) -> dict[uuid.UUID, list[str]]:
    """Which choices the applicant qualifies for, and why not otherwise.

    Computed once at submission and stored on each choice, rather than derived
    on read. A selector filtering 12,000 applications cannot re-derive this per
    row, and — more importantly — the answer must be the one that applied when
    the applicant submitted, not one recomputed after somebody edited the
    subject requirements in September.
    """
    qualifications = (
        session.execute(
            select(Qualification)
            .options(selectinload(Qualification.subjects))
            .where(Qualification.applicant_id == application.applicant_id)
        )
        .scalars()
        .all()
    )

    held: dict[str, float] = {}
    best_aggregate: float | None = None
    for qualification in qualifications:
        if qualification.aggregate is not None:
            value = float(qualification.aggregate)
            best_aggregate = value if best_aggregate is None else max(best_aggregate, value)
        for subject in qualification.subjects:
            points = float(subject.points) if subject.points is not None else 0.0
            held[subject.subject_code.upper()] = max(
                held.get(subject.subject_code.upper(), 0.0), points
            )

    findings: dict[uuid.UUID, list[str]] = {}
    for choice in application.choices:
        intake = session.get(ProgrammeIntake, choice.programme_intake_id)
        reasons: list[str] = []
        if intake is None:
            findings[choice.id] = ["This programme is no longer offered."]
            continue

        if intake.minimum_aggregate is not None:
            if best_aggregate is None:
                reasons.append("No verified aggregate score on file.")
            elif best_aggregate < float(intake.minimum_aggregate):
                reasons.append(
                    f"Aggregate {best_aggregate:g} is below the required "
                    f"{float(intake.minimum_aggregate):g}."
                )

        required: dict[str, Any] = intake.required_subjects or {}
        for code, minimum_points in (required.get("subjects") or {}).items():
            actual = held.get(str(code).upper())
            if actual is None:
                reasons.append(f"{code} is required and was not sat.")
            elif minimum_points is not None and actual < float(minimum_points):
                reasons.append(f"{code} is below the required grade.")

        findings[choice.id] = reasons

    return findings


def submit_application(
    session: Session, *, application: Application, actor_id: uuid.UUID
) -> Application:
    """Submit for consideration.

    The status it lands in depends on the scheme: `awaiting_fee` when the fee
    must settle before review, `submitted` otherwise. Not `under_review` —
    that is a human picking it up, and conflating the two makes the office's
    own queue meaningless.
    """
    if application.status != ApplicationStatus.DRAFT:
        raise Conflict("This application has already been submitted.")
    if not application.choices:
        raise RuleViolation(
            "Choose at least one programme before submitting.", rule="no_programme_choice"
        )

    scheme = session.get(AdmissionScheme, application.scheme_id)
    if scheme is None:  # pragma: no cover
        raise NotFound()
    now = utcnow()
    deadline = scheme.late_closes_at or scheme.closes_at
    if now > deadline:
        raise RuleViolation(f"Applications closed on {deadline:%d %B %Y}.", rule="scheme_closed")

    findings = check_eligibility(session, application=application)
    for choice in application.choices:
        reasons = findings.get(choice.id, [])
        choice.is_eligible = not reasons
        choice.ineligibility_reasons = reasons

    if all(not c.is_eligible for c in application.choices):
        # Refused, not flagged. Taking a fee for an application that cannot
        # succeed is the complaint that follows, and it is a fair one.
        raise RuleViolation(
            "You do not meet the entry requirements for any of your chosen programmes.",
            rule="no_eligible_choice",
            details={
                "choices": [
                    {"rank": c.rank, "reasons": c.ineligibility_reasons}
                    for c in application.choices
                ]
            },
        )

    before = {"status": application.status}
    application.status = (
        ApplicationStatus.AWAITING_FEE
        if scheme.requires_fee_before_review and scheme.application_fee_minor > 0
        else ApplicationStatus.SUBMITTED
    )
    application.submitted_at = now
    application.is_late = now > scheme.closes_at
    application.updated_by_id = actor_id

    for choice in application.choices:
        intake = session.get(ProgrammeIntake, choice.programme_intake_id)
        if intake is not None:
            intake.applications_received += 1

    if scheme.application_fee_minor > 0:
        from acmis.modules.finance import service as finance

        invoice = finance.raise_application_fee(
            session,
            applicant_id=application.applicant_id,
            scheme=scheme,
            is_late=application.is_late,
            actor_id=actor_id,
        )
        application.fee_invoice_id = invoice.id

    session.flush()
    _record_event(
        session,
        application,
        kind="submitted",
        message=(
            "Application submitted. It will be reviewed once the application fee is received."
            if application.status == ApplicationStatus.AWAITING_FEE
            else "Application submitted and queued for review."
        ),
        from_status=before["status"],
        to_status=application.status,
        actor_id=actor_id,
    )
    emit(
        "application:submit",
        AuditCategory.ADMISSION,
        resource_type="application",
        resource_id=application.id,
        resource_label=application.number,
        summary=f"Submitted with {len(application.choices)} choice(s)",
        changes=diff(before, {"status": application.status}),
        metadata={
            "eligible_choices": sum(1 for c in application.choices if c.is_eligible),
            "is_late": application.is_late,
        },
    )
    return application


def score_application(
    session: Session,
    *,
    application: Application,
    interview_score: float | None,
    entrance_exam_score: float | None,
    actor_id: uuid.UUID,
) -> Application:
    """Compute the ranking score under the scheme's weights.

    The weights used are copied onto the application. A scheme's weights are
    edited between rounds, and a score recomputed under the new ones is not the
    score the candidate was ranked on — which is exactly what an admissions
    appeal turns on.
    """
    scheme = session.get(AdmissionScheme, application.scheme_id)
    if scheme is None:  # pragma: no cover
        raise NotFound()

    before = {
        "aggregate_score": float(application.aggregate_score or 0),
        "final_score": float(application.final_score or 0),
    }
    if interview_score is not None:
        application.interview_score = interview_score
    if entrance_exam_score is not None:
        application.entrance_exam_score = entrance_exam_score

    weights: dict[str, float] = {k: float(v) for k, v in (scheme.scoring_weights or {}).items()}
    aggregate = _best_aggregate(session, application.applicant_id)
    application.aggregate_score = aggregate

    if weights:
        total = Decimal(0)
        components = {
            "aggregate": aggregate,
            "interview": (
                float(application.interview_score)
                if application.interview_score is not None
                else None
            ),
            "entrance_exam": (
                float(application.entrance_exam_score)
                if application.entrance_exam_score is not None
                else None
            ),
        }
        for key, weight in weights.items():
            value = components.get(key)
            if value is not None:
                total += Decimal(str(value)) * Decimal(str(weight))
        application.final_score = float(total)
    else:
        application.final_score = aggregate

    application.scoring_snapshot = {
        "weights": weights,
        "aggregate": aggregate,
        "interview": (
            float(application.interview_score) if application.interview_score is not None else None
        ),
        "entrance_exam": (
            float(application.entrance_exam_score)
            if application.entrance_exam_score is not None
            else None
        ),
        "scored_at": utcnow().isoformat(),
        "scheme_code": scheme.code,
    }
    application.scored_at = utcnow()
    application.updated_by_id = actor_id
    if application.status in {ApplicationStatus.SUBMITTED, ApplicationStatus.AWAITING_FEE}:
        application.status = ApplicationStatus.UNDER_REVIEW
    session.flush()

    emit(
        "application:score",
        AuditCategory.ADMISSION,
        resource_type="application",
        resource_id=application.id,
        resource_label=application.number,
        summary=f"Scored: final {application.final_score}",
        changes=diff(
            before,
            {
                "aggregate_score": float(application.aggregate_score or 0),
                "final_score": float(application.final_score or 0),
            },
        ),
        metadata={"weights": weights},
    )
    return application


def _best_aggregate(session: Session, applicant_id: uuid.UUID) -> float | None:
    value = session.execute(
        select(func.max(Qualification.aggregate)).where(Qualification.applicant_id == applicant_id)
    ).scalar()
    return float(value) if value is not None else None


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


def generate_selection_list(
    session: Session,
    *,
    scheme_id: uuid.UUID,
    programme_intake_id: uuid.UUID | None,
    name: str,
    method: str,
    minimum_score: float | None,
    round_number: int,
    actor_id: uuid.UUID,
) -> SelectionList:
    """Rank candidates and propose admit / waitlist / reject.

    Ranked by score, then by submission time. The tie-break matters: two
    candidates on the same score in the last seat is common, and "whoever
    applied first" is defensible in a way that "whichever row Postgres
    returned first" is not.

    Nothing is written to the applications here. The list is a proposal, and it
    is `approve_selection_list` — necessarily a different person — that applies
    it.
    """
    scheme = session.get(AdmissionScheme, scheme_id)
    if scheme is None or scheme.deleted_at is not None:
        raise NotFound("That admission scheme does not exist.")

    intake_ids: list[uuid.UUID]
    if programme_intake_id:
        intake_ids = [programme_intake_id]
    else:
        intake_ids = list(
            session.execute(
                select(ProgrammeIntake.id).where(
                    ProgrammeIntake.scheme_id == scheme_id,
                    ProgrammeIntake.deleted_at.is_(None),
                )
            ).scalars()
        )

    proposals: list[dict[str, Any]] = []
    admitted = waitlisted = rejected = 0
    cutoff: float | None = None

    for intake_id in intake_ids:
        intake = session.get(ProgrammeIntake, intake_id)
        if intake is None:
            continue

        rows = session.execute(
            select(ApplicationChoice, Application)
            .join(Application, ApplicationChoice.application_id == Application.id)
            .where(
                ApplicationChoice.programme_intake_id == intake_id,
                ApplicationChoice.is_eligible.is_(True),
                ApplicationChoice.deleted_at.is_(None),
                Application.deleted_at.is_(None),
                Application.status.in_(
                    [
                        ApplicationStatus.UNDER_REVIEW,
                        ApplicationStatus.SUBMITTED,
                        ApplicationStatus.INTERVIEW,
                        ApplicationStatus.RECOMMENDED,
                        ApplicationStatus.WAITLISTED,
                    ]
                ),
            )
            .order_by(
                Application.final_score.desc().nullslast(),
                Application.submitted_at.asc(),
            )
        ).all()

        seats = max(0, intake.approved_intake - intake.offers_accepted)
        # A modest waiting list. Long enough to absorb the usual declines,
        # short enough that being on it means something.
        waitlist_depth = max(5, seats // 5)

        for position, (choice, application) in enumerate(rows):
            score = float(application.final_score) if application.final_score is not None else None
            below_floor = minimum_score is not None and (score or 0) < minimum_score

            if position < seats and not below_floor:
                outcome = "admitted"
                admitted += 1
                cutoff = score if score is not None else cutoff
            elif position < seats + waitlist_depth and not below_floor:
                outcome = "waitlisted"
                waitlisted += 1
            else:
                outcome = "rejected"
                rejected += 1

            proposals.append(
                {
                    "application_id": str(application.id),
                    "application_number": application.number,
                    "choice_id": str(choice.id),
                    "programme_intake_id": str(intake_id),
                    "rank_in_list": position + 1,
                    "choice_rank": choice.rank,
                    "score": score,
                    "outcome": outcome,
                }
            )

    selection = SelectionList(
        scheme_id=scheme_id,
        programme_intake_id=programme_intake_id,
        name=name,
        round_number=round_number,
        status="draft",
        method=method,
        cutoff_score=cutoff,
        admitted_count=admitted,
        waitlisted_count=waitlisted,
        rejected_count=rejected,
        prepared_by_id=actor_id,
        generation_snapshot={
            "generated_at": utcnow().isoformat(),
            "method": method,
            "minimum_score": minimum_score,
            "intakes": [str(i) for i in intake_ids],
            "proposals": proposals,
        },
        created_by_id=actor_id,
    )
    session.add(selection)
    session.flush()

    emit(
        "selection_list:create",
        AuditCategory.ADMISSION,
        resource_type="selection_list",
        resource_id=selection.id,
        resource_label=selection.name,
        summary=(
            f"Proposed {admitted} admissions, {waitlisted} waitlisted, "
            f"{rejected} rejected (cut-off {cutoff})"
        ),
        metadata={"method": method, "round": round_number, "intakes": len(intake_ids)},
        severity="notice",
    )
    return selection


def approve_selection_list(
    session: Session, *, selection: SelectionList, actor_id: uuid.UUID, reason: str
) -> SelectionList:
    """Apply a proposed list to the applications.

    The self-approval check is in the policy bundle
    (`identity.separation-of-duties/no-self-approval`) and repeated here.
    Deliberate belt and braces: this write is irreversible in practice — 4,000
    applicants are told their outcome within minutes of it — and it should not
    depend on a single layer being configured correctly.
    """
    if selection.status != "draft":
        raise Conflict("This selection list has already been processed.")
    if selection.prepared_by_id == actor_id:
        raise RuleViolation(
            "A selection list must be approved by someone other than the person who prepared it.",
            rule="separation_of_duties",
        )

    proposals = (selection.generation_snapshot or {}).get("proposals", [])
    applied = 0
    for proposal in proposals:
        application = session.get(Application, uuid.UUID(proposal["application_id"]))
        if application is None or application.deleted_at is not None:
            continue
        choice = session.get(ApplicationChoice, uuid.UUID(proposal["choice_id"]))
        outcome = proposal["outcome"]

        application.decided_at = utcnow()
        application.decided_by_id = actor_id
        application.decision_reason = reason
        if choice is not None:
            choice.outcome = outcome
            choice.score = proposal.get("score")

        if outcome == "admitted":
            application.status = ApplicationStatus.ADMITTED
            application.admitted_choice_id = choice.id if choice else None
        elif outcome == "waitlisted":
            application.status = ApplicationStatus.WAITLISTED
            application.waitlist_position = proposal.get("rank_in_list")
        else:
            application.status = ApplicationStatus.REJECTED

        _record_event(
            session,
            application,
            kind="decision",
            message={
                "admitted": "Congratulations — you have been admitted.",
                "waitlisted": (
                    "You have been placed on the waiting list. You will be contacted if a "
                    "place becomes available."
                ),
                "rejected": "Your application was not successful on this occasion.",
            }[outcome],
            to_status=application.status,
            actor_id=actor_id,
        )
        applied += 1

    selection.status = "approved"
    selection.approved_by_id = actor_id
    selection.approved_at = utcnow()
    selection.notes = reason
    session.flush()

    emit(
        "selection_list:approve",
        AuditCategory.ADMISSION,
        resource_type="selection_list",
        resource_id=selection.id,
        resource_label=selection.name,
        summary=f"Approved; {applied} application(s) decided",
        metadata={"reason": reason, "applied": applied},
        severity="warning",
    )
    return selection


def issue_offers(
    session: Session, *, selection: SelectionList, engine: Any, actor_id: uuid.UUID
) -> dict[str, Any]:
    """Issue offers for the admitted candidates on an approved list.

    Each offer is authorized individually, because the intake-capacity rule
    reads the *current* `offers_issued` — so the ceiling binds at the offer
    that breaches it and the response names the programme, rather than the
    whole batch failing opaquely.
    """
    if selection.status != "approved":
        raise Conflict("Offers can only be issued from an approved selection list.")

    scheme = session.get(AdmissionScheme, selection.scheme_id)
    issued: list[str] = []
    refused: list[dict[str, str]] = []

    for proposal in (selection.generation_snapshot or {}).get("proposals", []):
        if proposal["outcome"] != "admitted":
            continue
        application = session.get(Application, uuid.UUID(proposal["application_id"]))
        if application is None or application.status != ApplicationStatus.ADMITTED:
            continue
        intake = session.get(ProgrammeIntake, uuid.UUID(proposal["programme_intake_id"]))
        if intake is None:
            continue

        capacity_check = decide(
            engine=engine,
            action="offer:issue",
            resource_type="offer",
            resource={
                "id": None,
                "application_id": str(application.id),
                "status": "pending",
                "approved_intake": intake.approved_intake,
                "offers_issued": intake.offers_issued,
            },
        )
        if not capacity_check.allowed:
            refused.append(
                {
                    "application_number": application.number,
                    "reason": capacity_check.reason,
                }
            )
            continue

        offer = Offer(
            application_id=application.id,
            programme_intake_id=intake.id,
            selection_list_id=selection.id,
            reference=f"OFR/{scheme.code if scheme else 'X'}/{secrets.token_hex(4).upper()}",
            status="issued",
            sponsorship="private",
            tuition_per_semester_minor=intake.tuition_per_semester_minor,
            issued_at=utcnow(),
            respond_by=(
                scheme.acceptance_deadline_on
                if scheme and scheme.acceptance_deadline_on
                else date.today() + timedelta(days=21)
            ),
            created_by_id=actor_id,
        )
        session.add(offer)
        intake.offers_issued += 1
        issued.append(application.number)

        _record_event(
            session,
            application,
            kind="offer_issued",
            message=f"Your admission offer {offer.reference} has been issued.",
            actor_id=actor_id,
        )

    session.flush()
    emit(
        "offer:issue",
        AuditCategory.ADMISSION,
        resource_type="selection_list",
        resource_id=selection.id,
        resource_label=selection.name,
        summary=f"{len(issued)} offer(s) issued, {len(refused)} refused",
        metadata={"refused": refused[:50]},
        severity="notice",
    )
    return {"issued": len(issued), "refused": refused}


def respond_to_offer(
    session: Session,
    *,
    offer: Offer,
    accept: bool,
    decline_reason: str | None,
    actor_id: uuid.UUID,
) -> Offer:
    if offer.status != "issued":
        raise Conflict("This offer has already been responded to or withdrawn.")
    if date.today() > offer.respond_by:
        raise RuleViolation(
            f"The deadline to respond was {offer.respond_by:%d %B %Y}.",
            rule="offer_expired",
            waivable_by=["admissions:approve_selection"],
        )

    application = session.get(Application, offer.application_id)
    intake = session.get(ProgrammeIntake, offer.programme_intake_id)
    now = utcnow()
    offer.responded_at = now

    if accept:
        offer.status = "accepted"
        if application is not None:
            application.status = ApplicationStatus.OFFER_ACCEPTED
            application.accepted_at = now
        if intake is not None:
            intake.offers_accepted += 1
        message = "You have accepted your offer. Enrolment instructions will follow."
    else:
        offer.status = "declined"
        if application is not None:
            application.status = ApplicationStatus.OFFER_DECLINED
            application.declined_at = now
            application.decline_reason = decline_reason
        message = "You have declined your offer."

    if application is not None:
        _record_event(
            session, application, kind="offer_response", message=message, actor_id=actor_id
        )
    session.flush()

    emit(
        "offer:respond",
        AuditCategory.ADMISSION,
        resource_type="offer",
        resource_id=offer.id,
        resource_label=offer.reference,
        summary=f"Offer {'accepted' if accept else 'declined'}",
        metadata={"decline_reason": decline_reason},
    )
    return offer


# ---------------------------------------------------------------------------
# Enrolment — the hand-off to the students module
# ---------------------------------------------------------------------------


def enrol(
    session: Session,
    *,
    offer: Offer,
    semester_id: uuid.UUID,
    student_number: str | None,
    actor_id: uuid.UUID,
) -> dict[str, Any]:
    """Create the student record from an accepted offer.

    One transaction across four modules — students, curriculum, finance,
    identity — which is the concrete reason this system is one process. Across
    services this is a saga, and the compensating action for "a student record
    was created and a fee invoice raised against it" is not something anyone
    wants to write or trust.

    Idempotent on the applicant: a second call returns the existing student
    rather than creating a twin. Double-enrolment is otherwise a genuinely
    common registry accident, and it is expensive to unpick because marks and
    invoices attach to both records.
    """
    from acmis.modules.curriculum.models import CurriculumVersion, Programme
    from acmis.modules.finance import service as finance
    from acmis.modules.students import service as students

    if offer.status != "accepted":
        raise Conflict("Only an accepted offer can be enrolled.")

    application = session.get(Application, offer.application_id)
    if application is None:
        raise NotFound()
    applicant = session.get(Applicant, application.applicant_id)
    if applicant is None:
        raise NotFound()

    if applicant.student_id:
        return {
            "student_id": str(applicant.student_id),
            "created": False,
            "message": "This applicant is already enrolled.",
        }

    intake = session.get(ProgrammeIntake, offer.programme_intake_id)
    if intake is None:
        raise NotFound("The programme intake no longer exists.")
    programme = session.get(Programme, intake.programme_id)
    if programme is None:
        raise NotFound("The programme no longer exists.")

    version = (
        session.execute(
            select(CurriculumVersion)
            .where(
                CurriculumVersion.programme_id == programme.id,
                CurriculumVersion.status == "approved",
                CurriculumVersion.deleted_at.is_(None),
            )
            .order_by(CurriculumVersion.cohort_from.desc())
        )
        .scalars()
        .first()
    )
    if version is None:
        raise RuleViolation(
            f"{programme.code} has no approved curriculum version, so a student cannot "
            "be attached to it.",
            rule="no_approved_curriculum",
        )

    student, student_programme, enrolment = students.create_from_admission(
        session,
        applicant=applicant,
        programme=programme,
        version=version,
        intake=intake,
        semester_id=semester_id,
        student_number=student_number,
        sponsorship=offer.sponsorship,
        actor_id=actor_id,
    )

    invoice = finance.raise_semester_invoice(
        session,
        student=student,
        student_programme=student_programme,
        semester_id=semester_id,
        actor_id=actor_id,
    )

    applicant.student_id = student.id
    application.status = ApplicationStatus.ENROLLED
    application.enrolled_at = utcnow()
    intake.enrolled_count += 1
    session.flush()

    _record_event(
        session,
        application,
        kind="enrolled",
        message=f"You are enrolled. Your student number is {student.student_number}.",
        to_status=ApplicationStatus.ENROLLED,
        actor_id=actor_id,
    )
    emit(
        "enrolment:create",
        AuditCategory.ENROLMENT,
        resource_type="student",
        resource_id=student.id,
        resource_label=f"{student.full_name} ({student.student_number})",
        summary=(
            f"Enrolled from application {application.number} onto {programme.code} "
            f"({version.version_label})"
        ),
        metadata={
            "application_id": str(application.id),
            "offer_reference": offer.reference,
            "programme": programme.code,
            "curriculum_version": version.version_label,
            "invoice_number": invoice.number,
        },
        severity="notice",
    )
    return {
        "student_id": str(student.id),
        "student_number": student.student_number,
        "student_programme_id": str(student_programme.id),
        "enrolment_id": str(enrolment.id),
        "invoice_number": invoice.number,
        "created": True,
    }


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def scheme_statistics(session: Session, *, scheme: AdmissionScheme) -> dict[str, Any]:
    by_status = (
        session.execute(
            select(Application.status, func.count())
            .where(Application.scheme_id == scheme.id, Application.deleted_at.is_(None))
            .group_by(Application.status)
            # `.all()` matters: `.tuples()` alone returns a streaming Result, and
            # this is read twice below — once for the mapping and once for the
            # total. The second pass on a consumed cursor silently sees nothing.
        )
        .tuples()
        .all()
    )

    intakes = (
        session.execute(
            select(ProgrammeIntake).where(
                ProgrammeIntake.scheme_id == scheme.id, ProgrammeIntake.deleted_at.is_(None)
            )
        )
        .scalars()
        .all()
    )

    return {
        "scheme": {"id": str(scheme.id), "code": scheme.code, "status": scheme.status},
        "by_status": dict(by_status),
        "total": sum(count for _status, count in by_status),
        "intakes": [
            {
                "programme_intake_id": str(i.id),
                "programme_id": str(i.programme_id),
                "approved_intake": i.approved_intake,
                "applications_received": i.applications_received,
                "offers_issued": i.offers_issued,
                "offers_accepted": i.offers_accepted,
                "enrolled": i.enrolled_count,
                "cutoff_score": float(i.cutoff_score) if i.cutoff_score else None,
                # The number a vice-chancellor asks for: applications per seat.
                "competition_ratio": (
                    round(i.applications_received / i.approved_intake, 2)
                    if i.approved_intake
                    else None
                ),
            }
            for i in intakes
        ],
    }


def _record_event(
    session: Session,
    application: Application,
    *,
    kind: str,
    message: str,
    from_status: str | None = None,
    to_status: str | None = None,
    actor_id: uuid.UUID | None = None,
    visible: bool = True,
) -> None:
    """The applicant-facing history.

    Separate from the audit trail on purpose: this is written for the applicant
    and the counter clerk, in their language. The audit trail records that a
    column changed; this records "your application was moved to interview".
    """
    session.add(
        ApplicationEvent(
            application_id=application.id,
            occurred_at=utcnow(),
            kind=kind,
            from_status=from_status,
            to_status=to_status,
            message=message,
            visible_to_applicant=visible,
            actor_id=actor_id,
        )
    )
