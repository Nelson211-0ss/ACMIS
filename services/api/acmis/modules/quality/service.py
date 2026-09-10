"""Quality assurance operations: registers, evaluations, observations, audits."""

from __future__ import annotations

import statistics
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from acmis.core.audit import AuditCategory, emit
from acmis.core.errors import Conflict, NotFound, RuleViolation
from acmis.core.models import utcnow
from acmis.modules.quality.models import (
    MIN_RESPONSES_TO_REPORT,
    AttendanceStatus,
    ClassSession,
    CourseEvaluation,
    EvaluationInstrument,
    EvaluationInvitation,
    EvaluationResponse,
    QualityIndicator,
    SessionAttendance,
    TeachingObservation,
)

log = structlog.get_logger(__name__)

#: Statuses that count as having turned up. `LATE` counts: a student who
#: arrived twenty minutes into a two-hour lecture attended it, and a threshold
#: that says otherwise measures punctuality while claiming to measure
#: attendance.
PRESENT_ENOUGH = frozenset({AttendanceStatus.PRESENT, AttendanceStatus.LATE})


# ---------------------------------------------------------------------------
# Class sessions and registers
# ---------------------------------------------------------------------------


def generate_sessions(
    session: Session,
    *,
    course_offering_id: uuid.UUID,
    semester_id: uuid.UUID,
    slots: list[dict[str, Any]],
    teaching_from: date,
    teaching_to: date,
    suspended_dates: set[date] | None = None,
    actor_id: uuid.UUID | None = None,
) -> list[ClassSession]:
    """Lay out a semester's classes from the timetable. Idempotent.

    `suspended_dates` are the public holidays and recess days from the
    academic calendar. Generating sessions over them produces a register
    nobody marks, and a course that looks two weeks behind because the
    denominator includes days the institution was shut.
    """
    suspended = suspended_dates or set()
    existing = {
        (row.session_date, row.starts_at)
        for row in session.execute(
            select(ClassSession).where(
                ClassSession.course_offering_id == course_offering_id,
                ClassSession.semester_id == semester_id,
                ClassSession.deleted_at.is_(None),
            )
        ).scalars()
    }

    created: list[ClassSession] = []
    for slot in slots:
        weekday = int(slot["weekday"])  # 0 = Monday
        cursor = teaching_from
        while cursor.weekday() != weekday:
            cursor += timedelta(days=1)
        week = 1
        while cursor <= teaching_to:
            if cursor not in suspended and (cursor, slot["starts_at"]) not in existing:
                row = ClassSession(
                    course_offering_id=course_offering_id,
                    semester_id=semester_id,
                    timetable_slot_id=slot.get("timetable_slot_id"),
                    kind=slot.get("kind", "lecture"),
                    session_date=cursor,
                    starts_at=slot["starts_at"],
                    ends_at=slot["ends_at"],
                    week_number=week,
                    room_id=slot.get("room_id"),
                    scheduled_staff_id=slot.get("staff_id"),
                    status="planned",
                    created_by_id=actor_id,
                )
                session.add(row)
                created.append(row)
            cursor += timedelta(days=7)
            week += 1

    session.flush()
    if created:
        emit(
            "class_session:generate",
            AuditCategory.QUALITY,
            resource_type="class_session",
            resource_id=course_offering_id,
            summary=f"Generated {len(created)} class session(s) for the semester",
        )
    return created


def mark_register(
    session: Session,
    *,
    class_session: ClassSession,
    entries: list[dict[str, Any]],
    actor_id: uuid.UUID | None,
    method: str = "roll_call",
) -> dict[str, Any]:
    """Record who was present. Re-markable until the register is closed.

    Absences are recorded explicitly rather than inferred from silence. A
    register where "no row" means "absent" cannot distinguish a student who
    missed the class from a class where the register was never marked — and
    those are a student problem and a teaching-delivery problem respectively.
    """
    if class_session.register_closed_at is not None:
        raise Conflict("This register is closed. A correction has to be raised as a dispute.")
    if class_session.status in ("cancelled", "not_held"):
        raise RuleViolation(
            f"This session was {class_session.status.replace('_', ' ')}, so there is no "
            "register to mark.",
            rule="session_not_held",
        )

    by_student = {
        row.student_id: row
        for row in session.execute(
            select(SessionAttendance).where(
                SessionAttendance.session_id == class_session.id,
                SessionAttendance.deleted_at.is_(None),
            )
        ).scalars()
    }

    now = utcnow()
    for entry in entries:
        student_id = entry["student_id"]
        status = entry.get("status", AttendanceStatus.PRESENT)
        if status == AttendanceStatus.EXCUSED and not entry.get("excuse_reason"):
            raise RuleViolation(
                "An excusal needs a reason; without one it is an absence somebody "
                "was kind about, and the threshold stops meaning anything.",
                rule="excuse_needs_reason",
                details={"student_id": str(student_id)},
            )
        row = by_student.get(student_id)
        if row is None:
            row = SessionAttendance(
                session_id=class_session.id,
                student_id=student_id,
                course_offering_id=class_session.course_offering_id,
                marked_at=now,
                created_by_id=actor_id,
            )
            session.add(row)
        row.status = status
        row.method = entry.get("method", method)
        row.minutes_late = entry.get("minutes_late")
        row.excuse_reason = entry.get("excuse_reason")
        row.excuse_attachment_id = entry.get("excuse_attachment_id")
        row.excused_by_id = actor_id if status == AttendanceStatus.EXCUSED else None
        row.marked_by_id = actor_id
        row.marked_at = now

    class_session.status = "held"
    if class_session.delivered_by_staff_id is None:
        class_session.delivered_by_staff_id = class_session.scheduled_staff_id
    session.flush()
    return _recount_session(session, class_session=class_session)


def _recount_session(session: Session, *, class_session: ClassSession) -> dict[str, Any]:
    rows = session.execute(
        select(SessionAttendance.status, func.count())
        .where(
            SessionAttendance.session_id == class_session.id,
            SessionAttendance.deleted_at.is_(None),
        )
        .group_by(SessionAttendance.status)
    ).all()
    counts = {str(status): int(total) for status, total in rows}
    marked = sum(counts.values())
    present = sum(counts.get(str(s), 0) for s in PRESENT_ENOUGH)
    # Excused absences leave the denominator: a student excused from a class
    # is neither present nor penalised, and counting them as absent turns an
    # accepted medical note into a threshold failure.
    excused = counts.get(str(AttendanceStatus.EXCUSED), 0)
    countable = marked - excused

    class_session.present_count = present
    class_session.expected_students = marked
    class_session.attendance_percent = (
        float(round(Decimal(present) / Decimal(countable) * 100, 2)) if countable else None
    )
    session.flush()
    return {
        "session_id": str(class_session.id),
        "marked": marked,
        "present": present,
        "excused": excused,
        "attendance_percent": class_session.attendance_percent,
        "by_status": counts,
    }


def close_register(
    session: Session, *, class_session: ClassSession, actor_id: uuid.UUID | None
) -> ClassSession:
    """Freeze a register. Corrections then go through the dispute path."""
    if class_session.register_closed_at is not None:
        raise Conflict("This register is already closed.")
    class_session.register_closed_at = utcnow()
    class_session.register_closed_by_id = actor_id
    session.flush()
    emit(
        "class_session:close_register",
        AuditCategory.QUALITY,
        resource_type="class_session",
        resource_id=class_session.id,
        summary=f"Register closed: {class_session.present_count} present",
    )
    return class_session


def cancel_session(
    session: Session,
    *,
    class_session: ClassSession,
    reason: str,
    actor_id: uuid.UUID | None,
    announced: bool = True,
) -> ClassSession:
    """Record that a class did not happen.

    `cancelled` (announced) and `not_held` (it simply did not happen) are kept
    apart, because the second is the one that matters: a course with four
    unannounced missing classes is a delivery failure, and a system that
    records both as "cancelled" hides it.
    """
    if class_session.register_closed_at is not None:
        raise Conflict("This register is closed.")
    class_session.status = "cancelled" if announced else "not_held"
    class_session.cancellation_reason = reason
    session.flush()
    emit(
        "class_session:cancel",
        AuditCategory.QUALITY,
        resource_type="class_session",
        resource_id=class_session.id,
        summary=f"{class_session.status.replace('_', ' ').capitalize()}: {reason}",
        severity="notice" if announced else "warning",
    )
    return class_session


def attendance_for_offering(
    session: Session, *, course_offering_id: uuid.UUID
) -> list[dict[str, Any]]:
    """Per-student attendance across the semester, rolled up.

    This is what feeds `assessment.AttendanceRecord` and therefore the
    examination gate. Computed from the sessions rather than incremented, so
    a corrected register corrects the percentage without a second write path
    that could disagree with it.
    """
    rows = session.execute(
        select(
            SessionAttendance.student_id,
            SessionAttendance.status,
            func.count(),
        )
        .join(ClassSession, ClassSession.id == SessionAttendance.session_id)
        .where(
            SessionAttendance.course_offering_id == course_offering_id,
            SessionAttendance.deleted_at.is_(None),
            ClassSession.status == "held",
        )
        .group_by(SessionAttendance.student_id, SessionAttendance.status)
    ).all()

    tally: dict[uuid.UUID, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for student_id, status, count in rows:
        tally[student_id][str(status)] = int(count)

    out: list[dict[str, Any]] = []
    for student_id, counts in tally.items():
        present = sum(counts.get(str(s), 0) for s in PRESENT_ENOUGH)
        excused = counts.get(str(AttendanceStatus.EXCUSED), 0)
        marked = sum(counts.values())
        countable = marked - excused
        out.append(
            {
                "student_id": str(student_id),
                "sessions_held": marked,
                "sessions_attended": present,
                "excused": excused,
                "percentage": (
                    float(round(Decimal(present) / Decimal(countable) * 100, 2))
                    if countable
                    else None
                ),
            }
        )
    return sorted(out, key=lambda row: row["percentage"] or 0)


def dispute_attendance(
    session: Session,
    *,
    attendance: SessionAttendance,
    note: str,
    actor_id: uuid.UUID | None,
) -> SessionAttendance:
    """A student challenges a mark. Recorded, not applied.

    Lodging a dispute never changes the mark: the correction is a separate,
    authorised act. A student who could flip their own absence to present by
    complaining has not disputed anything.
    """
    attendance.disputed_at = utcnow()
    attendance.dispute_note = note
    session.flush()
    emit(
        "session_attendance:dispute",
        AuditCategory.QUALITY,
        resource_type="session_attendance",
        resource_id=attendance.id,
        summary="Attendance disputed by the student",
        metadata={"note": note[:200]},
    )
    return attendance


def resolve_dispute(
    session: Session,
    *,
    attendance: SessionAttendance,
    status: str,
    actor_id: uuid.UUID | None,
    note: str | None = None,
) -> SessionAttendance:
    """Settle a dispute, with the resolver on the record.

    The database also requires both a note and a resolver before a closed
    register can change, so this is the only path that can correct one.
    """
    attendance.status = status
    attendance.resolved_by_id = actor_id
    attendance.dispute_note = (
        f"{attendance.dispute_note or ''}\n— resolved: {note}" if note else attendance.dispute_note
    )
    session.flush()
    emit(
        "session_attendance:resolve",
        AuditCategory.QUALITY,
        resource_type="session_attendance",
        resource_id=attendance.id,
        summary=f"Dispute resolved as {status}",
        severity="notice",
    )
    return attendance


def delivery_report(
    session: Session, *, semester_id: uuid.UUID, department_ids: list[uuid.UUID] | None = None
) -> dict[str, Any]:
    """Is the teaching that was promised actually happening?

    The one report in this module a head of department reads weekly. Ordered
    by the worst delivery rate, because that is the only end of the list
    anybody acts on.
    """
    stmt = (
        select(
            ClassSession.course_offering_id,
            ClassSession.status,
            func.count(),
        )
        .where(ClassSession.semester_id == semester_id, ClassSession.deleted_at.is_(None))
        .group_by(ClassSession.course_offering_id, ClassSession.status)
    )
    rows = session.execute(stmt).all()

    per_offering: dict[uuid.UUID, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for offering_id, status, count in rows:
        per_offering[offering_id][str(status)] = int(count)

    offerings: list[dict[str, Any]] = []
    for offering_id, counts in per_offering.items():
        planned = sum(counts.values())
        held = counts.get("held", 0)
        # Both kinds of miss, reported separately. An announced cancellation
        # is a decision; a class that simply did not happen is a failure.
        cancelled = counts.get("cancelled", 0)
        not_held = counts.get("not_held", 0)
        elapsed = held + cancelled + not_held
        offerings.append(
            {
                "course_offering_id": str(offering_id),
                "planned": planned,
                "held": held,
                "cancelled": cancelled,
                "not_held": not_held,
                "still_to_come": counts.get("planned", 0),
                "delivery_percent": (
                    float(round(Decimal(held) / Decimal(elapsed) * 100, 2)) if elapsed else None
                ),
            }
        )
    offerings.sort(key=lambda row: (row["delivery_percent"] is None, row["delivery_percent"] or 0))
    total_planned = sum(row["planned"] for row in offerings)
    total_held = sum(row["held"] for row in offerings)
    return {
        "semester_id": str(semester_id),
        "offerings": offerings,
        "sessions_planned": total_planned,
        "sessions_held": total_held,
        "unannounced_absences": sum(row["not_held"] for row in offerings),
    }


# ---------------------------------------------------------------------------
# Evaluations
# ---------------------------------------------------------------------------


def open_evaluation(
    session: Session,
    *,
    evaluation: CourseEvaluation,
    student_ids: list[uuid.UUID],
    actor_id: uuid.UUID | None,
) -> CourseEvaluation:
    """Invite a cohort and open the window.

    The invitation list is created here and is the only thing that stops a
    student responding twice. It records *that* they responded and never what
    they said — the two tables have no key between them, which is what makes
    the anonymity structural rather than procedural.
    """
    if evaluation.status not in ("scheduled", "open"):
        raise Conflict(f"A {evaluation.status} evaluation cannot be opened.")

    instrument = session.get(EvaluationInstrument, evaluation.instrument_id)
    if instrument is None or not instrument.is_published:
        raise RuleViolation(
            "The questionnaire has not been published, so responses could not be "
            "compared with any other run of it.",
            rule="instrument_not_published",
        )

    existing = {
        row.student_id
        for row in session.execute(
            select(EvaluationInvitation).where(
                EvaluationInvitation.evaluation_id == evaluation.id,
                EvaluationInvitation.deleted_at.is_(None),
            )
        ).scalars()
    }
    now = utcnow()
    for student_id in student_ids:
        if student_id in existing:
            continue
        session.add(
            EvaluationInvitation(
                evaluation_id=evaluation.id,
                student_id=student_id,
                invited_at=now,
                created_by_id=actor_id,
            )
        )
    evaluation.status = "open"
    evaluation.invited_count = len(existing | set(student_ids))
    session.flush()
    emit(
        "course_evaluation:open",
        AuditCategory.QUALITY,
        resource_type="course_evaluation",
        resource_id=evaluation.id,
        summary=f"Opened to {evaluation.invited_count} candidate(s)",
    )
    return evaluation


def submit_response(
    session: Session,
    *,
    evaluation: CourseEvaluation,
    student_id: uuid.UUID,
    answers: dict[str, Any],
    comments: str | None = None,
    year_of_study: int | None = None,
    study_mode: str | None = None,
) -> EvaluationResponse:
    """Record one anonymous return.

    Two writes, deliberately unlinked: the invitation is stamped as answered,
    and the response is stored with no identity on it at all. Nothing in the
    database can join them, and `evaluation_response` is append-only, so
    nobody can ever add a column to work backwards either.
    """
    now = utcnow()
    if not (evaluation.opens_at <= now <= evaluation.closes_at):
        raise Conflict("This evaluation is not open.")

    invitation = (
        session.execute(
            select(EvaluationInvitation).where(
                EvaluationInvitation.evaluation_id == evaluation.id,
                EvaluationInvitation.student_id == student_id,
                EvaluationInvitation.deleted_at.is_(None),
            )
        )
        .scalars()
        .first()
    )
    if invitation is None:
        raise RuleViolation("You were not invited to this evaluation.", rule="not_invited")
    if invitation.responded_at is not None:
        raise Conflict("You have already answered this evaluation.")

    response = EvaluationResponse(
        evaluation_id=evaluation.id,
        submitted_at=now,
        answers=answers,
        comments=comments,
        # Coarse only. A response tagged with anything finer than year and
        # mode identifies the respondent in a class of thirty.
        year_of_study=year_of_study,
        study_mode=study_mode,
    )
    session.add(response)
    invitation.responded_at = now
    evaluation.response_count += 1
    evaluation.is_reportable = evaluation.response_count >= MIN_RESPONSES_TO_REPORT
    session.flush()
    # Not audited against the student. An audit line naming who answered an
    # anonymous questionnaire would defeat the whole arrangement; the
    # invitation row already records that they did.
    return response


def close_evaluation(
    session: Session, *, evaluation: CourseEvaluation, actor_id: uuid.UUID | None
) -> CourseEvaluation:
    """Close the window and compute the summary once, for good.

    Stored rather than computed on read so a closed evaluation's numbers
    never move — which is what makes them citable in a promotion case a year
    later.
    """
    if evaluation.status == "closed":
        raise Conflict("This evaluation is already closed.")
    instrument = session.get(EvaluationInstrument, evaluation.instrument_id)
    questions = list(instrument.questions) if instrument is not None else []

    responses = (
        session.execute(
            select(EvaluationResponse).where(
                EvaluationResponse.evaluation_id == evaluation.id,
                EvaluationResponse.deleted_at.is_(None),
            )
        )
        .scalars()
        .all()
    )

    per_question: dict[str, list[float]] = defaultdict(list)
    for response in responses:
        for code, value in (response.answers or {}).items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                per_question[code].append(float(value))

    question_means = {
        code: round(statistics.fmean(values), 2) for code, values in per_question.items() if values
    }

    dimension_values: dict[str, list[float]] = defaultdict(list)
    for question in questions:
        # The instrument's questions are JSON authored through a form, so
        # every field is `Any` and both may be absent.
        dimension = str(question.get("dimension") or "")
        code = str(question.get("code") or "")
        if dimension and code in per_question:
            dimension_values[dimension].extend(per_question[code])
    dimension_means = {
        name: round(statistics.fmean(values), 2)
        for name, values in dimension_values.items()
        if values
    }

    evaluation.status = "closed"
    evaluation.closed_at = utcnow()
    evaluation.is_reportable = len(responses) >= MIN_RESPONSES_TO_REPORT
    evaluation.summary = {
        "responses": len(responses),
        "invited": evaluation.invited_count,
        "response_rate": (
            round(len(responses) / evaluation.invited_count * 100, 1)
            if evaluation.invited_count
            else None
        ),
        "questions": question_means,
        "dimensions": dimension_means,
        "overall": (
            round(statistics.fmean(list(question_means.values())), 2) if question_means else None
        ),
        # Recorded so a reader can see *why* nothing is shown, rather than
        # concluding the evaluation failed.
        "reporting_threshold": MIN_RESPONSES_TO_REPORT,
    }
    session.flush()
    emit(
        "course_evaluation:close",
        AuditCategory.QUALITY,
        resource_type="course_evaluation",
        resource_id=evaluation.id,
        summary=(
            f"Closed with {len(responses)} response(s)"
            + ("" if evaluation.is_reportable else "; below the reporting threshold")
        ),
    )
    return evaluation


def evaluation_results(
    session: Session, *, evaluation: CourseEvaluation, include_comments: bool
) -> dict[str, Any]:
    """The aggregate, and never the individual returns.

    Refuses below the threshold rather than returning an empty shell, so a
    caller cannot mistake "too few to report" for "nobody liked it".
    """
    if not evaluation.is_reportable:
        raise RuleViolation(
            f"Only {evaluation.response_count} response(s); at least "
            f"{MIN_RESPONSES_TO_REPORT} are needed before a breakdown can be shown "
            "without identifying the respondents.",
            rule="below_reporting_threshold",
            details={
                "responses": evaluation.response_count,
                "threshold": MIN_RESPONSES_TO_REPORT,
            },
        )
    payload: dict[str, Any] = {
        "evaluation_id": str(evaluation.id),
        "status": evaluation.status,
        **(evaluation.summary or {}),
    }
    if include_comments:
        # Comments are released on a stricter rule than the scores: a comment
        # can identify its author by content alone, so the head of department
        # reads them and a published report does not.
        payload["comments"] = [
            row.comments
            for row in session.execute(
                select(EvaluationResponse).where(
                    EvaluationResponse.evaluation_id == evaluation.id,
                    EvaluationResponse.comments.is_not(None),
                    EvaluationResponse.deleted_at.is_(None),
                )
            ).scalars()
            if (row.comments or "").strip()
        ]
    return payload


# ---------------------------------------------------------------------------
# Observations
# ---------------------------------------------------------------------------


def submit_observation(
    session: Session, *, observation: TeachingObservation, actor_id: uuid.UUID | None
) -> TeachingObservation:
    """Send an observation to the person observed.

    It goes to them *first*, and their response is part of the record. An
    observation the observed member of staff has not seen is not an
    observation, it is a report about them.
    """
    if observation.status not in ("draft", "returned"):
        raise Conflict(f"This observation is {observation.status}.")
    scores = [
        float(entry["score"])
        for entry in (observation.rubric_scores or [])
        if isinstance(entry, dict) and isinstance(entry.get("score"), (int, float))
    ]
    observation.overall_score = round(statistics.fmean(scores), 2) if scores else None
    observation.status = "awaiting_response"
    session.flush()
    emit(
        "teaching_observation:submit",
        AuditCategory.QUALITY,
        resource_type="teaching_observation",
        resource_id=observation.id,
        summary="Observation shared with the member of staff observed",
    )
    return observation


def acknowledge_observation(
    session: Session,
    *,
    observation: TeachingObservation,
    response: str | None,
    actor_id: uuid.UUID | None,
) -> TeachingObservation:
    observation.observee_response = response
    observation.acknowledged_at = utcnow()
    observation.status = "closed"
    session.flush()
    emit(
        "teaching_observation:acknowledge",
        AuditCategory.QUALITY,
        resource_type="teaching_observation",
        resource_id=observation.id,
        summary="Acknowledged by the member of staff observed",
    )
    return observation


# ---------------------------------------------------------------------------
# Indicators
# ---------------------------------------------------------------------------


def record_indicator(
    session: Session,
    *,
    code: str,
    name: str,
    value: float,
    computed_at: datetime | None = None,
    target: float | None = None,
    numerator: float | None = None,
    denominator: float | None = None,
    unit_id: uuid.UUID | None = None,
    programme_id: uuid.UUID | None = None,
    academic_year_id: uuid.UUID | None = None,
    semester_id: uuid.UUID | None = None,
    method_note: str | None = None,
    actor_id: uuid.UUID | None = None,
    higher_is_better: bool = True,
) -> QualityIndicator:
    """Store one measurement.

    The target is copied in beside the value, so a historical breach stays a
    breach after the target moves. Comparing last year's number against this
    year's target is how an institution talks itself out of a finding.
    """
    performance = "unknown"
    if target is not None:
        if value == target:
            performance = "at"
        elif (value > target) == higher_is_better:
            performance = "above"
        else:
            performance = "below"

    row = QualityIndicator(
        code=code,
        name=name,
        unit_id=unit_id,
        programme_id=programme_id,
        academic_year_id=academic_year_id,
        semester_id=semester_id,
        value=value,
        target=target,
        performance=performance,
        numerator=numerator,
        denominator=denominator,
        method_note=method_note,
        computed_at=computed_at or utcnow(),
        computed_by_id=actor_id,
    )
    session.add(row)
    session.flush()
    return row


def observation_summary(
    session: Session, *, staff_id: uuid.UUID, developmental_only: bool = True
) -> dict[str, Any]:
    """A member of staff's own observation history."""
    stmt = select(TeachingObservation).where(
        TeachingObservation.staff_id == staff_id,
        TeachingObservation.deleted_at.is_(None),
    )
    if developmental_only:
        stmt = stmt.where(TeachingObservation.is_developmental.is_(True))
    rows = session.execute(stmt.order_by(TeachingObservation.observed_on.desc())).scalars().all()
    scores = [float(row.overall_score) for row in rows if row.overall_score is not None]
    return {
        "observations": len(rows),
        "mean_score": round(statistics.fmean(scores), 2) if scores else None,
        "latest": rows[0].observed_on.isoformat() if rows else None,
        "outstanding_actions": sum(
            1 for row in rows if row.follow_up_due_on and row.follow_up_due_on >= date.today()
        ),
    }


def evaluation_state(session: Session, *, evaluation_id: uuid.UUID) -> CourseEvaluation:
    row = session.get(CourseEvaluation, evaluation_id)
    if row is None or row.deleted_at is not None:
        raise NotFound()
    return row
