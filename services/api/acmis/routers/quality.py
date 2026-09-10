"""Quality assurance: registers, evaluations, observations, audits, indicators."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query, status
from pydantic import Field
from sqlalchemy import func, select

from acmis.core.abac import authorize
from acmis.core.audit import AuditCategory, emit
from acmis.core.deps import AnyContext, PageQuery, StaffContext, StudentContext
from acmis.core.errors import Conflict, NotFound, RuleViolation
from acmis.core.models import utcnow
from acmis.core.pagination import keyset_page
from acmis.core.schemas import Page, Reason, Schema
from acmis.modules.curriculum.models import Course, CourseOffering
from acmis.modules.quality import service
from acmis.modules.quality.models import (
    MIN_RESPONSES_TO_REPORT,
    AttendanceStatus,
    ClassSession,
    CourseEvaluation,
    EvaluationInstrument,
    EvaluationInvitation,
    QualityAudit,
    QualityIndicator,
    SessionAttendance,
    StaffAttendance,
    TeachingObservation,
)
from acmis.routers._common import get_or_404

router = APIRouter(prefix="/quality", tags=["quality"])


# ---------------------------------------------------------------------------
# Class sessions and attendance
# ---------------------------------------------------------------------------


class SessionOut(Schema):
    id: uuid.UUID
    course_offering_id: uuid.UUID
    semester_id: uuid.UUID
    kind: str
    session_date: date
    starts_at: str
    ends_at: str
    week_number: int | None
    room_id: uuid.UUID | None
    scheduled_staff_id: uuid.UUID | None
    delivered_by_staff_id: uuid.UUID | None
    status: str
    topic: str | None
    expected_students: int
    present_count: int
    attendance_percent: float | None
    register_closed_at: datetime | None


class GenerateSessionsIn(Schema):
    semester_id: uuid.UUID
    teaching_from: date
    teaching_to: date
    #: [{weekday: 0-6, starts_at: "08:00", ends_at: "10:00", kind, room_id,
    #:   staff_id, timetable_slot_id}]
    slots: Annotated[list[dict[str, Any]], Field(min_length=1, max_length=40)]
    #: Public holidays and recess days from the academic calendar. Generating
    #: sessions over them produces registers nobody marks and a course that
    #: looks behind because the denominator counts days the campus was shut.
    suspended_dates: list[date] = Field(default_factory=list)


@router.post("/offerings/{offering_id}/sessions", response_model=dict)
def generate_sessions(
    offering_id: uuid.UUID, payload: GenerateSessionsIn, ctx: StaffContext
) -> dict[str, Any]:
    """Lay out a semester of classes from the timetable. Idempotent."""
    authorize(
        engine=ctx.engine,
        action="class_session:create",
        resource_type="class_session",
        resource={
            "id": None,
            "course_offering_id": str(offering_id),
            "semester_id": str(payload.semester_id),
            "status": "planned",
            "register_closed": False,
            "delivered_by_staff_id": None,
            "scheduled_staff_id": None,
            "department_ids": [str(d) for d in ctx.principal.department_ids],
            "faculty_ids": [str(f) for f in ctx.principal.faculty_ids],
        },
        category=AuditCategory.QUALITY,
    )
    created = service.generate_sessions(
        ctx.db,
        course_offering_id=offering_id,
        semester_id=payload.semester_id,
        slots=payload.slots,
        teaching_from=payload.teaching_from,
        teaching_to=payload.teaching_to,
        suspended_dates=set(payload.suspended_dates),
        actor_id=ctx.principal.id,
    )
    return {"created": len(created), "course_offering_id": str(offering_id)}


@router.get("/offerings/{offering_id}/sessions", response_model=Page[SessionOut])
def list_sessions(
    offering_id: uuid.UUID,
    ctx: AnyContext,
    page: PageQuery,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
) -> Page[SessionOut]:
    authorize(
        engine=ctx.engine,
        action="class_session:list",
        resource_type="class_session",
        resource={
            "id": None,
            "course_offering_id": str(offering_id),
            "semester_id": None,
            "status": status_filter,
            "register_closed": False,
            "delivered_by_staff_id": None,
            "scheduled_staff_id": None,
            "department_ids": [str(d) for d in ctx.principal.department_ids],
            "faculty_ids": [str(f) for f in ctx.principal.faculty_ids],
        },
        category=AuditCategory.QUALITY,
    )
    stmt = select(ClassSession).where(
        ClassSession.course_offering_id == offering_id, ClassSession.deleted_at.is_(None)
    )
    if status_filter:
        stmt = stmt.where(ClassSession.status == status_filter)
    found = keyset_page(
        ctx.db, stmt, page=page, key=ClassSession.session_date, ident=ClassSession.id
    )
    return Page.of(
        [SessionOut.model_validate(row) for row in found.rows],
        limit=page.limit,
        next_cursor=found.next_cursor,
        total=found.total,
    )


class AttendanceEntry(Schema):
    student_id: uuid.UUID
    status: Annotated[str, Field(pattern="^(present|absent|late|excused)$")] = "present"
    minutes_late: Annotated[int | None, Field(ge=0, le=600)] = None
    excuse_reason: Annotated[str | None, Field(max_length=300)] = None
    excuse_attachment_id: uuid.UUID | None = None
    method: Annotated[str | None, Field(max_length=20)] = None


class MarkRegisterIn(Schema):
    entries: Annotated[list[AttendanceEntry], Field(min_length=1, max_length=1000)]
    method: Annotated[str, Field(max_length=20)] = "roll_call"
    topic: Annotated[str | None, Field(max_length=300)] = None
    delivered_by_staff_id: uuid.UUID | None = None


@router.post("/sessions/{session_id}/register", response_model=dict)
def mark_register(
    session_id: uuid.UUID, payload: MarkRegisterIn, ctx: StaffContext
) -> dict[str, Any]:
    """Mark who was present. Absences recorded explicitly, not inferred."""
    class_session = get_or_404(ctx, ClassSession, session_id)
    authorize(
        engine=ctx.engine,
        action="session_attendance:mark",
        resource_type="class_session",
        resource=class_session,
        category=AuditCategory.QUALITY,
    )
    if payload.topic:
        class_session.topic = payload.topic
    if payload.delivered_by_staff_id:
        class_session.delivered_by_staff_id = payload.delivered_by_staff_id
    return service.mark_register(
        ctx.db,
        class_session=class_session,
        entries=[entry.model_dump() for entry in payload.entries],
        actor_id=ctx.principal.id,
        method=payload.method,
    )


@router.post("/sessions/{session_id}/close", response_model=SessionOut)
def close_register(session_id: uuid.UUID, ctx: StaffContext) -> SessionOut:
    class_session = get_or_404(ctx, ClassSession, session_id)
    authorize(
        engine=ctx.engine,
        action="class_session:close",
        resource_type="class_session",
        resource=class_session,
        category=AuditCategory.QUALITY,
    )
    return SessionOut.model_validate(
        service.close_register(ctx.db, class_session=class_session, actor_id=ctx.principal.id)
    )


class CancelSessionIn(Reason):
    #: An announced cancellation and a class that simply did not happen are
    #: different facts, and only the second is a delivery failure.
    announced: bool = True


@router.post("/sessions/{session_id}/cancel", response_model=SessionOut)
def cancel_session(
    session_id: uuid.UUID, payload: CancelSessionIn, ctx: StaffContext
) -> SessionOut:
    class_session = get_or_404(ctx, ClassSession, session_id)
    authorize(
        engine=ctx.engine,
        action="class_session:update",
        resource_type="class_session",
        resource=class_session,
        category=AuditCategory.QUALITY,
    )
    return SessionOut.model_validate(
        service.cancel_session(
            ctx.db,
            class_session=class_session,
            reason=payload.reason,
            actor_id=ctx.principal.id,
            announced=payload.announced,
        )
    )


@router.post("/sessions/{session_id}/check-in", status_code=status.HTTP_204_NO_CONTENT)
def check_in(session_id: uuid.UUID, ctx: StudentContext) -> None:
    """Self-service attendance, where the institution uses it.

    Recorded with its method, because a tap from a phone is not a roll call
    and a dispute turns on which one it was.
    """
    class_session = get_or_404(ctx, ClassSession, session_id)
    authorize(
        engine=ctx.engine,
        action="session_attendance:check_in",
        resource_type="class_session",
        resource=class_session,
        category=AuditCategory.QUALITY,
    )
    service.mark_register(
        ctx.db,
        class_session=class_session,
        entries=[{"student_id": ctx.student_id, "status": AttendanceStatus.PRESENT}],
        actor_id=ctx.principal.id,
        method="self_service",
    )


@router.get("/offerings/{offering_id}/attendance", response_model=list[dict[str, Any]])
def offering_attendance(offering_id: uuid.UUID, ctx: StaffContext) -> list[dict[str, Any]]:
    """Per-student attendance for the semester, worst first."""
    authorize(
        engine=ctx.engine,
        action="session_attendance:list",
        resource_type="class_session",
        resource={
            "id": None,
            "course_offering_id": str(offering_id),
            "semester_id": None,
            "status": "held",
            "register_closed": True,
            "delivered_by_staff_id": None,
            "scheduled_staff_id": None,
            "department_ids": [str(d) for d in ctx.principal.department_ids],
            "faculty_ids": [str(f) for f in ctx.principal.faculty_ids],
        },
        category=AuditCategory.QUALITY,
    )
    return service.attendance_for_offering(ctx.db, course_offering_id=offering_id)


@router.get("/me/attendance", response_model=list[dict[str, Any]])
def my_attendance(ctx: StudentContext) -> list[dict[str, Any]]:
    """A student's own attendance, by course.

    Attendance gates examinations, so a student who cannot see this finds out
    they are barred in the week of the paper.
    """
    rows = ctx.db.execute(
        select(
            SessionAttendance.course_offering_id,
            SessionAttendance.status,
            func.count(),
        )
        .join(ClassSession, ClassSession.id == SessionAttendance.session_id)
        .where(
            SessionAttendance.student_id == ctx.student_id,
            SessionAttendance.deleted_at.is_(None),
            ClassSession.status == "held",
        )
        .group_by(SessionAttendance.course_offering_id, SessionAttendance.status)
    ).all()

    per_offering: dict[uuid.UUID, dict[str, int]] = {}
    for offering_id, state, count in rows:
        per_offering.setdefault(offering_id, {})[str(state)] = int(count)

    # The offering id alone is unreadable to a student. One extra query names
    # the courses rather than making the portal resolve a dozen ids one by one.
    labels: dict[uuid.UUID, tuple[str, str]] = {}
    if per_offering:
        for offering_id, code, title in ctx.db.execute(
            select(CourseOffering.id, Course.code, Course.title)
            .join(Course, Course.id == CourseOffering.course_id)
            .where(CourseOffering.id.in_(list(per_offering)))
        ).all():
            labels[offering_id] = (str(code), str(title))

    out: list[dict[str, Any]] = []
    for offering_id, counts in per_offering.items():
        present = counts.get("present", 0) + counts.get("late", 0)
        excused = counts.get("excused", 0)
        countable = sum(counts.values()) - excused
        code, title = labels.get(offering_id, ("", ""))
        out.append(
            {
                "course_offering_id": str(offering_id),
                "course_code": code,
                "course_title": title,
                "sessions": sum(counts.values()),
                "attended": present,
                "excused": excused,
                "percentage": round(present * 100 / countable, 1) if countable else None,
                "by_status": counts,
            }
        )
    out.sort(key=lambda row: str(row["course_code"]))
    return out


@router.post("/attendance/{attendance_id}/dispute", response_model=dict)
def dispute_attendance(
    attendance_id: uuid.UUID, payload: Reason, ctx: StudentContext
) -> dict[str, Any]:
    """Challenge a mark. Recorded, never applied by the student."""
    attendance = get_or_404(ctx, SessionAttendance, attendance_id)
    authorize(
        engine=ctx.engine,
        action="session_attendance:dispute",
        resource_type="session_attendance",
        resource=attendance,
        category=AuditCategory.QUALITY,
    )
    row = service.dispute_attendance(
        ctx.db, attendance=attendance, note=payload.reason, actor_id=ctx.principal.id
    )
    return {"attendance_id": str(row.id), "disputed_at": row.disputed_at}


class ResolveDisputeIn(Reason):
    status: Annotated[str, Field(pattern="^(present|absent|late|excused)$")]


@router.post("/attendance/{attendance_id}/resolve", response_model=dict)
def resolve_dispute(
    attendance_id: uuid.UUID, payload: ResolveDisputeIn, ctx: StaffContext
) -> dict[str, Any]:
    attendance = get_or_404(ctx, SessionAttendance, attendance_id)
    authorize(
        engine=ctx.engine,
        action="session_attendance:update",
        resource_type="session_attendance",
        resource=attendance,
        category=AuditCategory.QUALITY,
    )
    row = service.resolve_dispute(
        ctx.db,
        attendance=attendance,
        status=payload.status,
        actor_id=ctx.principal.id,
        note=payload.reason,
    )
    return {"attendance_id": str(row.id), "status": row.status}


@router.get("/delivery", response_model=dict)
def delivery(semester_id: uuid.UUID, ctx: StaffContext) -> dict[str, Any]:
    """Is the teaching that was promised actually happening?

    The one report here a head of department reads weekly. Worst delivery
    first, because that is the only end of the list anybody acts on.
    """
    authorize(
        engine=ctx.engine,
        action="class_session:list",
        resource_type="class_session",
        resource={
            "id": None,
            "course_offering_id": None,
            "semester_id": str(semester_id),
            "status": "held",
            "register_closed": False,
            "delivered_by_staff_id": None,
            "scheduled_staff_id": None,
            "department_ids": [str(d) for d in ctx.principal.department_ids],
            "faculty_ids": [str(f) for f in ctx.principal.faculty_ids],
        },
        category=AuditCategory.QUALITY,
    )
    return service.delivery_report(ctx.db, semester_id=semester_id)


# ---------------------------------------------------------------------------
# Staff attendance
# ---------------------------------------------------------------------------


class StaffAttendanceOut(Schema):
    id: uuid.UUID
    staff_id: uuid.UUID
    attendance_date: date
    kind: str
    status: str
    checked_in_at: datetime | None
    checked_out_at: datetime | None
    hours: float | None
    payable: bool
    payroll_period: str | None


class StaffAttendanceIn(Schema):
    staff_id: uuid.UUID
    attendance_date: date
    kind: Annotated[str, Field(max_length=20)] = "duty"
    status: Annotated[str, Field(pattern="^(present|absent|late|excused)$")] = "present"
    class_session_id: uuid.UUID | None = None
    checked_in_at: datetime | None = None
    checked_out_at: datetime | None = None
    hours: Annotated[float | None, Field(ge=0, le=24)] = None
    payable: bool = False
    absence_reason: Annotated[str | None, Field(max_length=300)] = None


@router.post(
    "/staff-attendance", response_model=StaffAttendanceOut, status_code=status.HTTP_201_CREATED
)
def record_staff_attendance(payload: StaffAttendanceIn, ctx: StaffContext) -> StaffAttendanceOut:
    """Duty attendance for a rota or a session-paid contract."""
    authorize(
        engine=ctx.engine,
        action="staff_attendance:create",
        resource_type="staff_attendance",
        resource={
            "id": None,
            "staff_id": str(payload.staff_id),
            "kind": payload.kind,
            "status": payload.status,
            "payable": payload.payable,
            "department_ids": [str(d) for d in ctx.principal.department_ids],
            "faculty_ids": [str(f) for f in ctx.principal.faculty_ids],
        },
        category=AuditCategory.QUALITY,
    )
    row = StaffAttendance(
        recorded_by_id=ctx.principal.id, created_by_id=ctx.principal.id, **payload.model_dump()
    )
    ctx.db.add(row)
    ctx.db.flush()
    return StaffAttendanceOut.model_validate(row)


@router.get("/staff-attendance", response_model=Page[StaffAttendanceOut])
def list_staff_attendance(
    ctx: StaffContext,
    page: PageQuery,
    staff_id: uuid.UUID | None = None,
    payable_only: bool = False,
) -> Page[StaffAttendanceOut]:
    authorize(
        engine=ctx.engine,
        action="staff_attendance:list",
        resource_type="staff_attendance",
        resource={
            "id": None,
            "staff_id": str(staff_id) if staff_id else None,
            "kind": "duty",
            "status": "present",
            "payable": payable_only,
            "department_ids": [str(d) for d in ctx.principal.department_ids],
            "faculty_ids": [str(f) for f in ctx.principal.faculty_ids],
        },
        category=AuditCategory.QUALITY,
    )
    stmt = select(StaffAttendance).where(StaffAttendance.deleted_at.is_(None))
    if staff_id:
        stmt = stmt.where(StaffAttendance.staff_id == staff_id)
    if payable_only:
        stmt = stmt.where(StaffAttendance.payable.is_(True))
    found = keyset_page(
        ctx.db,
        stmt,
        page=page,
        key=StaffAttendance.attendance_date,
        ident=StaffAttendance.id,
        descending=True,
    )
    return Page.of(
        [StaffAttendanceOut.model_validate(row) for row in found.rows],
        limit=page.limit,
        next_cursor=found.next_cursor,
        total=found.total,
    )


# ---------------------------------------------------------------------------
# Evaluations
# ---------------------------------------------------------------------------


class InstrumentOut(Schema):
    id: uuid.UUID
    code: str
    version: int
    name: str
    scope: str
    introduction: str | None
    questions: list[dict[str, Any]]
    dimensions: list[str]
    is_published: bool


class InstrumentIn(Schema):
    code: Annotated[str, Field(max_length=40)]
    name: Annotated[str, Field(max_length=200)]
    scope: Annotated[str, Field(max_length=20)] = "teaching"
    introduction: str | None = None
    questions: Annotated[list[dict[str, Any]], Field(min_length=1, max_length=100)]
    dimensions: list[str] = Field(default_factory=list)


@router.get("/instruments", response_model=list[InstrumentOut])
def list_instruments(ctx: AnyContext, published_only: bool = True) -> list[InstrumentOut]:
    authorize(
        engine=ctx.engine,
        action="evaluation_instrument:list",
        resource_type="evaluation_instrument",
        resource={"id": None, "scope": "teaching", "is_published": published_only},
    )
    stmt = select(EvaluationInstrument).where(EvaluationInstrument.deleted_at.is_(None))
    if published_only:
        stmt = stmt.where(EvaluationInstrument.is_published.is_(True))
    rows = (
        ctx.db.execute(
            stmt.order_by(EvaluationInstrument.code, EvaluationInstrument.version.desc())
        )
        .scalars()
        .all()
    )
    return [InstrumentOut.model_validate(row) for row in rows]


@router.post("/instruments", response_model=InstrumentOut, status_code=status.HTTP_201_CREATED)
def create_instrument(payload: InstrumentIn, ctx: StaffContext) -> InstrumentOut:
    """Author a questionnaire.

    A new *version* rather than an edit whenever one is already in use: a
    question reworded between semesters makes a trend meaningless, and the
    numbers are compared across years.
    """
    authorize(
        engine=ctx.engine,
        action="evaluation_instrument:create",
        resource_type="evaluation_instrument",
        resource={"id": None, "scope": payload.scope, "is_published": False},
        category=AuditCategory.QUALITY,
    )
    latest = ctx.db.execute(
        select(func.coalesce(func.max(EvaluationInstrument.version), 0)).where(
            EvaluationInstrument.code == payload.code
        )
    ).scalar_one()
    instrument = EvaluationInstrument(
        version=int(latest) + 1, created_by_id=ctx.principal.id, **payload.model_dump()
    )
    ctx.db.add(instrument)
    ctx.db.flush()
    emit(
        "evaluation_instrument:create",
        AuditCategory.QUALITY,
        resource_type="evaluation_instrument",
        resource_id=instrument.id,
        resource_label=f"{instrument.name} v{instrument.version}",
        summary=f"Questionnaire drafted with {len(payload.questions)} question(s)",
    )
    return InstrumentOut.model_validate(instrument)


@router.post("/instruments/{instrument_id}/publish", response_model=InstrumentOut)
def publish_instrument(instrument_id: uuid.UUID, ctx: StaffContext) -> InstrumentOut:
    instrument = get_or_404(ctx, EvaluationInstrument, instrument_id)
    authorize(
        engine=ctx.engine,
        action="evaluation_instrument:publish",
        resource_type="evaluation_instrument",
        resource=instrument,
        category=AuditCategory.QUALITY,
    )
    if instrument.is_published:
        raise Conflict("This questionnaire is already published.")
    instrument.is_published = True
    instrument.published_at = utcnow()
    ctx.db.flush()
    return InstrumentOut.model_validate(instrument)


class EvaluationOut(Schema):
    id: uuid.UUID
    instrument_id: uuid.UUID
    course_offering_id: uuid.UUID
    semester_id: uuid.UUID
    staff_id: uuid.UUID | None
    opens_at: datetime
    closes_at: datetime
    results_visible_from: datetime | None
    status: str
    invited_count: int
    response_count: int
    is_reportable: bool


class EvaluationIn(Schema):
    instrument_id: uuid.UUID
    course_offering_id: uuid.UUID
    semester_id: uuid.UUID
    staff_id: uuid.UUID | None = None
    opens_at: datetime
    closes_at: datetime
    #: Deliberately after the marking deadline: a lecturer must not read
    #: their students' opinions while still holding their marks.
    results_visible_from: datetime | None = None


@router.post("/evaluations", response_model=EvaluationOut, status_code=status.HTTP_201_CREATED)
def create_evaluation(payload: EvaluationIn, ctx: StaffContext) -> EvaluationOut:
    authorize(
        engine=ctx.engine,
        action="course_evaluation:create",
        resource_type="course_evaluation",
        resource={
            "id": None,
            "course_offering_id": str(payload.course_offering_id),
            "semester_id": str(payload.semester_id),
            "staff_id": str(payload.staff_id) if payload.staff_id else None,
            "status": "scheduled",
            "is_reportable": False,
            "results_visible": False,
            "is_open": False,
            "department_ids": [str(d) for d in ctx.principal.department_ids],
            "faculty_ids": [str(f) for f in ctx.principal.faculty_ids],
        },
        category=AuditCategory.QUALITY,
    )
    evaluation = CourseEvaluation(
        status="scheduled", created_by_id=ctx.principal.id, **payload.model_dump()
    )
    ctx.db.add(evaluation)
    ctx.db.flush()
    return EvaluationOut.model_validate(evaluation)


@router.get("/evaluations", response_model=Page[EvaluationOut])
def list_evaluations(
    ctx: StaffContext,
    page: PageQuery,
    semester_id: uuid.UUID | None = None,
    course_offering_id: uuid.UUID | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    mine_only: bool = False,
) -> Page[EvaluationOut]:
    """Evaluation runs.

    The quality office needs this across the institution and a lecturer needs
    it for their own; `mine_only` is the difference, and it is honest about
    which listing is being asked for so the policy can decide accordingly.
    """
    authorize(
        engine=ctx.engine,
        action="course_evaluation:list",
        resource_type="course_evaluation",
        resource={
            "id": None,
            "course_offering_id": str(course_offering_id) if course_offering_id else None,
            "semester_id": str(semester_id) if semester_id else None,
            "staff_id": str(ctx.staff_id) if mine_only else None,
            "status": status_filter,
            "is_reportable": True,
            "results_visible": True,
            "is_open": False,
            "department_ids": [str(d) for d in ctx.principal.department_ids],
            "faculty_ids": [str(f) for f in ctx.principal.faculty_ids],
        },
        category=AuditCategory.QUALITY,
    )
    stmt = select(CourseEvaluation).where(CourseEvaluation.deleted_at.is_(None))
    if semester_id:
        stmt = stmt.where(CourseEvaluation.semester_id == semester_id)
    if course_offering_id:
        stmt = stmt.where(CourseEvaluation.course_offering_id == course_offering_id)
    if status_filter:
        stmt = stmt.where(CourseEvaluation.status == status_filter)
    if mine_only:
        stmt = stmt.where(CourseEvaluation.staff_id == ctx.staff_id)
    found = keyset_page(
        ctx.db,
        stmt,
        page=page,
        key=CourseEvaluation.closes_at,
        ident=CourseEvaluation.id,
        descending=True,
    )
    return Page.of(
        [EvaluationOut.model_validate(row) for row in found.rows],
        limit=page.limit,
        next_cursor=found.next_cursor,
        total=found.total,
    )


class OpenEvaluationIn(Schema):
    student_ids: Annotated[list[uuid.UUID], Field(min_length=1, max_length=5000)]


@router.post("/evaluations/{evaluation_id}/open", response_model=EvaluationOut)
def open_evaluation(
    evaluation_id: uuid.UUID, payload: OpenEvaluationIn, ctx: StaffContext
) -> EvaluationOut:
    evaluation = get_or_404(ctx, CourseEvaluation, evaluation_id)
    authorize(
        engine=ctx.engine,
        action="course_evaluation:open",
        resource_type="course_evaluation",
        resource=evaluation,
        category=AuditCategory.QUALITY,
    )
    return EvaluationOut.model_validate(
        service.open_evaluation(
            ctx.db,
            evaluation=evaluation,
            student_ids=payload.student_ids,
            actor_id=ctx.principal.id,
        )
    )


class ResponseIn(Schema):
    #: {question_code: value}
    answers: dict[str, Any]
    comments: Annotated[str | None, Field(max_length=4000)] = None
    year_of_study: Annotated[int | None, Field(ge=1, le=12)] = None
    study_mode: Annotated[str | None, Field(max_length=20)] = None


@router.post("/evaluations/{evaluation_id}/responses", status_code=status.HTTP_204_NO_CONTENT)
def submit_response(evaluation_id: uuid.UUID, payload: ResponseIn, ctx: StudentContext) -> None:
    """Answer a questionnaire.

    Returns nothing at all — not even an id. A response identifier handed back
    to the browser is a handle somebody could later use to find the row, and
    the whole arrangement rests on there being no such handle.
    """
    evaluation = get_or_404(ctx, CourseEvaluation, evaluation_id)
    authorize(
        engine=ctx.engine,
        action="evaluation_response:create",
        resource_type="course_evaluation",
        resource=evaluation,
        category=AuditCategory.QUALITY,
    )
    service.submit_response(
        ctx.db,
        evaluation=evaluation,
        student_id=ctx.student_id,
        answers=payload.answers,
        comments=payload.comments,
        year_of_study=payload.year_of_study,
        study_mode=payload.study_mode,
    )


@router.get("/me/evaluations", response_model=list[dict[str, Any]])
def my_evaluations(ctx: StudentContext) -> list[dict[str, Any]]:
    """ "You have two evaluations to complete."

    The invitation says *that* the student was asked and whether they
    answered — never what they said.
    """
    rows = ctx.db.execute(
        select(EvaluationInvitation, CourseEvaluation)
        .join(CourseEvaluation, CourseEvaluation.id == EvaluationInvitation.evaluation_id)
        .where(
            EvaluationInvitation.student_id == ctx.student_id,
            EvaluationInvitation.deleted_at.is_(None),
        )
        .order_by(CourseEvaluation.closes_at)
    ).all()
    out: list[dict[str, Any]] = []
    for invitation, evaluation in rows:
        authorize(
            engine=ctx.engine,
            action="evaluation_invitation:read",
            resource_type="evaluation_invitation",
            resource=invitation,
        )
        out.append(
            {
                "evaluation_id": str(evaluation.id),
                "instrument_id": str(evaluation.instrument_id),
                "course_offering_id": str(evaluation.course_offering_id),
                "opens_at": evaluation.opens_at.isoformat(),
                "closes_at": evaluation.closes_at.isoformat(),
                "answered": invitation.responded_at is not None,
                "declined": invitation.declined_at is not None,
            }
        )
    return out


@router.post("/evaluations/{evaluation_id}/close", response_model=EvaluationOut)
def close_evaluation(evaluation_id: uuid.UUID, ctx: StaffContext) -> EvaluationOut:
    evaluation = get_or_404(ctx, CourseEvaluation, evaluation_id)
    authorize(
        engine=ctx.engine,
        action="course_evaluation:close",
        resource_type="course_evaluation",
        resource=evaluation,
        category=AuditCategory.QUALITY,
    )
    return EvaluationOut.model_validate(
        service.close_evaluation(ctx.db, evaluation=evaluation, actor_id=ctx.principal.id)
    )


@router.get("/evaluations/{evaluation_id}/results", response_model=dict)
def evaluation_results(
    evaluation_id: uuid.UUID, ctx: StaffContext, include_comments: bool = False
) -> dict[str, Any]:
    """The aggregate, and never the individual returns.

    Refuses below the reporting threshold rather than returning an empty
    shell, so nobody mistakes "too few to report" for "nobody liked it".
    """
    evaluation = get_or_404(ctx, CourseEvaluation, evaluation_id)
    authorize(
        engine=ctx.engine,
        action="course_evaluation:read_results",
        resource_type="course_evaluation",
        resource=evaluation,
        category=AuditCategory.QUALITY,
        audit_reads=True,
    )
    return service.evaluation_results(
        ctx.db, evaluation=evaluation, include_comments=include_comments
    )


class ReflectionIn(Schema):
    reflection: Annotated[str, Field(min_length=10, max_length=8000)]
    action_plan: Annotated[str | None, Field(max_length=8000)] = None


@router.post("/evaluations/{evaluation_id}/reflect", response_model=EvaluationOut)
def submit_reflection(
    evaluation_id: uuid.UUID, payload: ReflectionIn, ctx: StaffContext
) -> EvaluationOut:
    """The lecturer's written response to what the students said.

    The step that makes an evaluation a conversation rather than a verdict,
    and the one an external reviewer looks for.
    """
    evaluation = get_or_404(ctx, CourseEvaluation, evaluation_id)
    authorize(
        engine=ctx.engine,
        action="course_evaluation:reflect",
        resource_type="course_evaluation",
        resource=evaluation,
        category=AuditCategory.QUALITY,
    )
    evaluation.staff_reflection = payload.reflection
    evaluation.reflection_submitted_at = utcnow()
    if payload.action_plan:
        evaluation.action_plan = payload.action_plan
    ctx.db.flush()
    emit(
        "course_evaluation:reflect",
        AuditCategory.QUALITY,
        resource_type="course_evaluation",
        resource_id=evaluation.id,
        summary="Reflection submitted by the member of staff evaluated",
    )
    return EvaluationOut.model_validate(evaluation)


# ---------------------------------------------------------------------------
# Observations
# ---------------------------------------------------------------------------


class ObservationOut(Schema):
    id: uuid.UUID
    staff_id: uuid.UUID
    observer_staff_id: uuid.UUID
    course_offering_id: uuid.UUID | None
    observed_on: date
    purpose: str
    rubric_scores: list[dict[str, Any]]
    overall_score: float | None
    strengths: str | None
    areas_to_develop: str | None
    agreed_actions: str | None
    observee_response: str | None
    is_developmental: bool
    status: str
    follow_up_due_on: date | None


class ObservationIn(Schema):
    staff_id: uuid.UUID
    course_offering_id: uuid.UUID | None = None
    class_session_id: uuid.UUID | None = None
    observed_on: date
    purpose: Annotated[str, Field(max_length=30)] = "peer"
    rubric_scores: list[dict[str, Any]] = Field(default_factory=list)
    strengths: str | None = None
    areas_to_develop: str | None = None
    agreed_actions: str | None = None
    is_developmental: bool = True
    follow_up_due_on: date | None = None


@router.post("/observations", response_model=ObservationOut, status_code=status.HTTP_201_CREATED)
def create_observation(payload: ObservationIn, ctx: StaffContext) -> ObservationOut:
    authorize(
        engine=ctx.engine,
        action="teaching_observation:create",
        resource_type="teaching_observation",
        resource={
            "id": None,
            "staff_id": str(payload.staff_id),
            "observer_staff_id": str(ctx.staff_id),
            "purpose": payload.purpose,
            "status": "draft",
            "is_developmental": payload.is_developmental,
            "department_ids": [str(d) for d in ctx.principal.department_ids],
            "faculty_ids": [str(f) for f in ctx.principal.faculty_ids],
        },
        category=AuditCategory.QUALITY,
    )
    observation = TeachingObservation(
        observer_staff_id=ctx.staff_id,
        status="draft",
        created_by_id=ctx.principal.id,
        **payload.model_dump(),
    )
    ctx.db.add(observation)
    ctx.db.flush()
    return ObservationOut.model_validate(observation)


@router.post("/observations/{observation_id}/submit", response_model=ObservationOut)
def submit_observation(observation_id: uuid.UUID, ctx: StaffContext) -> ObservationOut:
    """Share it with the person observed. They see it first."""
    observation = get_or_404(ctx, TeachingObservation, observation_id)
    authorize(
        engine=ctx.engine,
        action="teaching_observation:submit",
        resource_type="teaching_observation",
        resource=observation,
        category=AuditCategory.QUALITY,
    )
    return ObservationOut.model_validate(
        service.submit_observation(ctx.db, observation=observation, actor_id=ctx.principal.id)
    )


class ObservationResponseIn(Schema):
    response: Annotated[str | None, Field(max_length=8000)] = None


@router.post("/observations/{observation_id}/acknowledge", response_model=ObservationOut)
def acknowledge_observation(
    observation_id: uuid.UUID, payload: ObservationResponseIn, ctx: StaffContext
) -> ObservationOut:
    observation = get_or_404(ctx, TeachingObservation, observation_id)
    authorize(
        engine=ctx.engine,
        action="teaching_observation:respond",
        resource_type="teaching_observation",
        resource=observation,
        category=AuditCategory.QUALITY,
    )
    return ObservationOut.model_validate(
        service.acknowledge_observation(
            ctx.db,
            observation=observation,
            response=payload.response,
            actor_id=ctx.principal.id,
        )
    )


@router.get("/observations", response_model=Page[ObservationOut])
def list_observations(
    ctx: StaffContext,
    page: PageQuery,
    staff_id: uuid.UUID | None = None,
    mine_only: bool = True,
) -> Page[ObservationOut]:
    # The class-level resource describes the *class*, not a pretend row. An
    # earlier version filled in `staff_id` with the caller's own — which made
    # every listing look like a request for their own observations, so
    # `observee-reads-own-observation` permitted it and the confidentiality
    # deny never fired. A member of staff could read a colleague's
    # developmental observation through the rule meant to show them their own.
    decision = authorize(
        engine=ctx.engine,
        action="teaching_observation:list",
        resource_type="teaching_observation",
        resource={
            "id": None,
            # Truthful about which listing is being asked for. `mine_only`
            # really is a request for the caller's own, so saying so lets
            # `observee-reads-own-observation` permit it; a request for
            # somebody else's says `None` and falls to the confidentiality
            # rules, which is what closed the leak.
            "staff_id": str(ctx.staff_id) if mine_only else (str(staff_id) if staff_id else None),
            "observer_staff_id": str(ctx.staff_id) if mine_only else None,
            "purpose": "peer",
            "status": "closed",
            "is_developmental": True,
            "department_ids": [str(d) for d in ctx.principal.department_ids],
            "faculty_ids": [str(f) for f in ctx.principal.faculty_ids],
        },
        category=AuditCategory.QUALITY,
    )
    stmt = select(TeachingObservation).where(TeachingObservation.deleted_at.is_(None))
    if mine_only or staff_id is None:
        # And the query is narrowed to what the caller may see regardless of
        # the decision above: their own, and the ones they wrote. A permit
        # granted for the class is not a permit over everybody's.
        stmt = stmt.where(
            (TeachingObservation.staff_id == ctx.staff_id)
            | (TeachingObservation.observer_staff_id == ctx.staff_id)
        )
    else:
        stmt = stmt.where(TeachingObservation.staff_id == staff_id)
    found = keyset_page(
        ctx.db,
        stmt,
        page=page,
        key=TeachingObservation.observed_on,
        ident=TeachingObservation.id,
        descending=True,
    )
    items = [
        ObservationOut.model_construct(
            **decision.filter(ObservationOut.model_validate(row).model_dump())
        )
        for row in found.rows
    ]
    return Page.of(items, limit=page.limit, next_cursor=found.next_cursor, total=found.total)


# ---------------------------------------------------------------------------
# Audits and indicators
# ---------------------------------------------------------------------------


class AuditOut(Schema):
    id: uuid.UUID
    reference: str
    title: str
    kind: str
    unit_id: uuid.UUID | None
    programme_id: uuid.UUID | None
    standard: str | None
    conducted_on: date | None
    findings: list[dict[str, Any]]
    major_findings: int
    minor_findings: int
    open_findings: int
    overall_outcome: str | None
    status: str
    next_review_due_on: date | None


class AuditIn(Schema):
    title: Annotated[str, Field(max_length=200)]
    kind: Annotated[str, Field(max_length=30)] = "internal"
    unit_id: uuid.UUID | None = None
    programme_id: uuid.UUID | None = None
    standard: Annotated[str | None, Field(max_length=200)] = None
    period_from: date | None = None
    period_to: date | None = None
    conducted_on: date | None = None
    panel_staff_ids: list[uuid.UUID] = Field(default_factory=list)
    external_panel: list[str] = Field(default_factory=list)
    #: [{code, severity, finding, evidence, owner_staff_id, due_on}]
    findings: list[dict[str, Any]] = Field(default_factory=list)
    overall_outcome: Annotated[str | None, Field(max_length=60)] = None
    next_review_due_on: date | None = None


@router.post("/audits", response_model=AuditOut, status_code=status.HTTP_201_CREATED)
def create_audit(payload: AuditIn, ctx: StaffContext) -> AuditOut:
    """Open a quality audit.

    Every finding needs an owner and a date. A finding with neither is a
    sentence in a report and nothing else, so they are counted here and the
    counts drive the overdue-actions view.
    """
    authorize(
        engine=ctx.engine,
        action="quality_audit:create",
        resource_type="quality_audit",
        resource={
            "id": None,
            "kind": payload.kind,
            "unit_id": str(payload.unit_id) if payload.unit_id else None,
            "programme_id": str(payload.programme_id) if payload.programme_id else None,
            "status": "planned",
            "department_ids": [str(d) for d in ctx.principal.department_ids],
            "faculty_ids": [str(f) for f in ctx.principal.faculty_ids],
        },
        category=AuditCategory.QUALITY,
    )
    if not payload.unit_id and not payload.programme_id:
        raise RuleViolation(
            "An audit has to be of something: a unit or a programme.",
            rule="audit_scope_required",
        )
    unowned = [
        entry.get("code") or entry.get("finding", "")[:40]
        for entry in payload.findings
        if entry.get("severity") in ("major", "minor")
        and not (entry.get("owner_staff_id") and entry.get("due_on"))
    ]
    if unowned:
        raise RuleViolation(
            "Every major and minor finding needs an owner and a date by which it "
            "closes. Without them it is a sentence in a report.",
            rule="finding_needs_owner",
            details={"findings": unowned},
        )

    sequence = (
        int(
            ctx.db.execute(
                select(func.count()).where(QualityAudit.deleted_at.is_(None))
            ).scalar_one()
        )
        + 1
    )
    row = QualityAudit(
        reference=f"QA/{date.today().year}/{sequence:04d}",
        lead_auditor_id=ctx.principal.id,
        status="planned",
        created_by_id=ctx.principal.id,
        **payload.model_dump(),
    )
    row.major_findings = sum(1 for entry in payload.findings if entry.get("severity") == "major")
    row.minor_findings = sum(1 for entry in payload.findings if entry.get("severity") == "minor")
    row.open_findings = sum(
        1 for entry in payload.findings if entry.get("status", "open") == "open"
    )
    ctx.db.add(row)
    ctx.db.flush()
    emit(
        "quality_audit:create",
        AuditCategory.QUALITY,
        resource_type="quality_audit",
        resource_id=row.id,
        resource_label=row.reference,
        summary=(
            f"{payload.kind.capitalize()} audit opened with {row.major_findings} major "
            f"and {row.minor_findings} minor finding(s)"
        ),
    )
    return AuditOut.model_validate(row)


@router.get("/audits", response_model=Page[AuditOut])
def list_audits(
    ctx: StaffContext,
    page: PageQuery,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    open_findings_only: bool = False,
) -> Page[AuditOut]:
    authorize(
        engine=ctx.engine,
        action="quality_audit:list",
        resource_type="quality_audit",
        resource={
            "id": None,
            "kind": "internal",
            "unit_id": None,
            "programme_id": None,
            "status": status_filter,
            "department_ids": [str(d) for d in ctx.principal.department_ids],
            "faculty_ids": [str(f) for f in ctx.principal.faculty_ids],
        },
        category=AuditCategory.QUALITY,
    )
    stmt = select(QualityAudit).where(QualityAudit.deleted_at.is_(None))
    if status_filter:
        stmt = stmt.where(QualityAudit.status == status_filter)
    if open_findings_only:
        stmt = stmt.where(QualityAudit.open_findings > 0)
    found = keyset_page(
        ctx.db,
        stmt,
        page=page,
        key=QualityAudit.conducted_on,
        ident=QualityAudit.id,
        descending=True,
        nulls="first",
    )
    return Page.of(
        [AuditOut.model_validate(row) for row in found.rows],
        limit=page.limit,
        next_cursor=found.next_cursor,
        total=found.total,
    )


class CloseFindingIn(Reason):
    finding_code: Annotated[str, Field(max_length=40)]


@router.post("/audits/{audit_id}/close-finding", response_model=AuditOut)
def close_finding(audit_id: uuid.UUID, payload: CloseFindingIn, ctx: StaffContext) -> AuditOut:
    """Close one finding, with the evidence that closed it."""
    row = get_or_404(ctx, QualityAudit, audit_id)
    authorize(
        engine=ctx.engine,
        action="quality_audit:close_finding",
        resource_type="quality_audit",
        resource=row,
        category=AuditCategory.QUALITY,
    )
    findings = [dict(entry) for entry in row.findings]
    matched = False
    for entry in findings:
        if entry.get("code") == payload.finding_code:
            entry["status"] = "closed"
            entry["closed_on"] = date.today().isoformat()
            entry["closure_note"] = payload.reason
            matched = True
    if not matched:
        raise NotFound()
    row.findings = findings
    row.open_findings = sum(1 for entry in findings if entry.get("status", "open") == "open")
    ctx.db.flush()
    emit(
        "quality_audit:close_finding",
        AuditCategory.QUALITY,
        resource_type="quality_audit",
        resource_id=row.id,
        resource_label=row.reference,
        summary=f"Finding {payload.finding_code} closed",
    )
    return AuditOut.model_validate(row)


class IndicatorOut(Schema):
    id: uuid.UUID
    code: str
    name: str
    unit_id: uuid.UUID | None
    programme_id: uuid.UUID | None
    academic_year_id: uuid.UUID | None
    value: float
    target: float | None
    performance: str | None
    numerator: float | None
    denominator: float | None
    computed_at: datetime


@router.get("/indicators", response_model=Page[IndicatorOut])
def list_indicators(
    ctx: StaffContext,
    page: PageQuery,
    code: Annotated[str | None, Query(max_length=60)] = None,
    unit_id: uuid.UUID | None = None,
    below_target_only: bool = False,
) -> Page[IndicatorOut]:
    authorize(
        engine=ctx.engine,
        action="quality_indicator:list",
        resource_type="quality_indicator",
        resource={
            "id": None,
            "code": code,
            "unit_id": str(unit_id) if unit_id else None,
            "programme_id": None,
            "performance": "below" if below_target_only else None,
        },
        category=AuditCategory.QUALITY,
    )
    stmt = select(QualityIndicator).where(QualityIndicator.deleted_at.is_(None))
    if code:
        stmt = stmt.where(QualityIndicator.code == code)
    if unit_id:
        stmt = stmt.where(QualityIndicator.unit_id == unit_id)
    if below_target_only:
        stmt = stmt.where(QualityIndicator.performance == "below")
    found = keyset_page(
        ctx.db,
        stmt,
        page=page,
        key=QualityIndicator.computed_at,
        ident=QualityIndicator.id,
        descending=True,
    )
    return Page.of(
        [IndicatorOut.model_validate(row) for row in found.rows],
        limit=page.limit,
        next_cursor=found.next_cursor,
        total=found.total,
    )


class IndicatorIn(Schema):
    code: Annotated[str, Field(max_length=60)]
    name: Annotated[str, Field(max_length=200)]
    value: float
    target: float | None = None
    numerator: float | None = None
    denominator: float | None = None
    unit_id: uuid.UUID | None = None
    programme_id: uuid.UUID | None = None
    academic_year_id: uuid.UUID | None = None
    semester_id: uuid.UUID | None = None
    method_note: str | None = None
    higher_is_better: bool = True


@router.post("/indicators", response_model=IndicatorOut, status_code=status.HTTP_201_CREATED)
def record_indicator(payload: IndicatorIn, ctx: StaffContext) -> IndicatorOut:
    authorize(
        engine=ctx.engine,
        action="quality_indicator:create",
        resource_type="quality_indicator",
        resource={
            "id": None,
            "code": payload.code,
            "unit_id": str(payload.unit_id) if payload.unit_id else None,
            "programme_id": str(payload.programme_id) if payload.programme_id else None,
            "performance": None,
        },
        category=AuditCategory.QUALITY,
    )
    return IndicatorOut.model_validate(
        service.record_indicator(ctx.db, actor_id=ctx.principal.id, **payload.model_dump())
    )


@router.get("/reporting-threshold", response_model=dict)
def reporting_threshold(ctx: AnyContext) -> dict[str, Any]:
    """Why an evaluation with four responses shows nothing.

    Published so the answer is discoverable rather than a support question.
    """
    return {
        "minimum_responses": MIN_RESPONSES_TO_REPORT,
        "reason": (
            "Below this, a breakdown identifies the respondents — 'three of four "
            "disagreed' names the dissenter in a class of four."
        ),
    }
