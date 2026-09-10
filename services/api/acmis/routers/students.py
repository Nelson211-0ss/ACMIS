"""Student life-cycle and bio-data endpoints."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query, status
from pydantic import Field
from sqlalchemy import func, select

from acmis.core.abac import authorize, enforce_writable
from acmis.core.audit import AuditCategory
from acmis.core.deps import AnyContext, PageQuery, StaffContext, StudentContext
from acmis.core.pagination import keyset_page
from acmis.core.schemas import Page, Reason, RecordEnvelope, Schema
from acmis.modules.students import service
from acmis.modules.students.models import (
    Clearance,
    Registration,
    StatusChange,
    Student,
    StudentProgramme,
)
from acmis.routers._common import get_or_404

router = APIRouter(prefix="/students", tags=["students"])


class ProgrammeAttachmentOut(Schema):
    id: uuid.UUID
    programme_id: uuid.UUID
    curriculum_version_id: uuid.UUID
    entry_route: str
    sponsorship: str
    sponsor_name: str | None
    current_year_of_study: int
    current_semester_number: int
    cgpa: float | None
    credits_earned: int
    credits_required: int
    outstanding_retakes: int
    progression_status: str
    is_primary: bool
    started_on: date
    expected_completion_on: date | None


class StudentOut(Schema):
    id: uuid.UUID
    student_number: str
    surname: str
    given_names: str
    other_names: str | None
    date_of_birth: date
    sex: str
    nationality: str
    district_of_origin: str | None
    email: str
    phone: str
    status: str
    admitted_on: date
    residence: str | None
    #: Dropped rather than nulled when masked — see `RecordEnvelope`.
    national_id: str | None = None
    bank_account_number: str | None = None
    disability: str | None = None
    disability_detail: str | None = None
    medical_conditions: str | None = None
    next_of_kin_name: str | None = None
    next_of_kin_phone: str | None = None
    holds: list[dict[str, Any]] = Field(default_factory=list)
    programmes: list[ProgrammeAttachmentOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


@router.get("", response_model=Page[StudentOut])
def list_students(
    ctx: StaffContext,
    page: PageQuery,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    programme_id: uuid.UUID | None = None,
    faculty_id: uuid.UUID | None = None,
    year_of_study: int | None = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> Page[StudentOut]:
    """List students within the caller's reach.

    Two layers again: the policy decides whether they may list students at all,
    and the query is then narrowed to their own units. A dean who passes
    another faculty's id gets their own faculties, not an error — the filter is
    intersected with their reach rather than trusted.
    """
    decision = authorize(
        engine=ctx.engine,
        action="student:list",
        resource_type="student",
        resource={"id": None, "status": status_filter},
        category=AuditCategory.STUDENT_RECORD,
    )

    stmt = select(Student).where(Student.deleted_at.is_(None))
    if status_filter:
        stmt = stmt.where(Student.status == status_filter)
    if programme_id:
        stmt = stmt.where(Student.programme_ids.overlap([programme_id]))

    reach = ctx.principal.faculty_ids | ctx.principal.department_ids
    if reach and "student:manage" not in ctx.principal.permissions:
        wanted = (
            [faculty_id]
            if faculty_id and faculty_id in ctx.principal.faculty_ids
            else sorted(reach)
        )
        stmt = stmt.where(
            Student.faculty_ids.overlap(wanted) | Student.department_ids.overlap(wanted)
        )
    elif faculty_id:
        stmt = stmt.where(Student.faculty_ids.overlap([faculty_id]))

    if search:
        term = f"%{search.lower()}%"
        stmt = stmt.where(
            func.lower(Student.surname).like(term)
            | func.lower(Student.given_names).like(term)
            | func.lower(Student.student_number).like(term)
        )
    if year_of_study:
        stmt = stmt.join(StudentProgramme).where(
            StudentProgramme.current_year_of_study == year_of_study,
            StudentProgramme.is_primary.is_(True),
        )

    found = keyset_page(
        ctx.db,
        stmt,
        page=page,
        key=func.concat_ws(" ", Student.surname, Student.given_names),
        ident=Student.id,
    )

    items = [
        StudentOut.model_construct(**decision.filter(StudentOut.model_validate(r).model_dump()))
        for r in found.rows
    ]
    return Page.of(items, limit=page.limit, next_cursor=found.next_cursor, total=found.total)


@router.get("/{student_id}", response_model=RecordEnvelope[StudentOut])
def get_student(student_id: uuid.UUID, ctx: AnyContext) -> RecordEnvelope[StudentOut]:
    student = get_or_404(ctx, Student, student_id)
    decision = authorize(
        engine=ctx.engine,
        action="student:read",
        resource_type="student",
        resource=student,
        category=AuditCategory.STUDENT_RECORD,
    )
    payload = StudentOut.model_validate(student).model_dump()
    return RecordEnvelope(
        data=StudentOut.model_construct(**decision.filter(payload)),
        capabilities=service.capabilities_for(ctx, student),
        masked_fields=sorted(decision.masked_fields),
    )


@router.get("/me/record", response_model=RecordEnvelope[StudentOut])
def my_record(ctx: StudentContext) -> RecordEnvelope[StudentOut]:
    student = get_or_404(ctx, Student, ctx.student_id)
    decision = authorize(
        engine=ctx.engine,
        action="student:read",
        resource_type="student",
        resource=student,
        category=AuditCategory.STUDENT_RECORD,
    )
    payload = StudentOut.model_validate(student).model_dump()
    return RecordEnvelope(
        data=StudentOut.model_construct(**decision.filter(payload)),
        capabilities=service.capabilities_for(ctx, student),
        masked_fields=sorted(decision.masked_fields),
    )


class StudentUpdateIn(Schema):
    phone: str | None = None
    alternate_phone: str | None = None
    personal_email: str | None = None
    postal_address: str | None = None
    residential_address: str | None = None
    residence: str | None = None
    room_number: str | None = None
    next_of_kin_name: str | None = None
    next_of_kin_relationship: str | None = None
    next_of_kin_phone: str | None = None
    emergency_contact_name: str | None = None
    emergency_contact_phone: str | None = None
    bank_name: str | None = None
    bank_account_name: str | None = None
    bank_account_number: str | None = None
    mobile_money_number: str | None = None
    certificate_name: str | None = None
    #: Registry-owned. A student sending these gets a 422 naming the fields,
    #: because the decision's writable-field set does not include them.
    surname: str | None = None
    given_names: str | None = None
    date_of_birth: date | None = None
    disability: str | None = None
    medical_conditions: str | None = None
    exam_accommodations: str | None = None


@router.patch("/{student_id}", response_model=StudentOut)
def update_student(student_id: uuid.UUID, payload: StudentUpdateIn, ctx: AnyContext) -> StudentOut:
    student = get_or_404(ctx, Student, student_id)
    decision = authorize(
        engine=ctx.engine,
        action="student:update",
        resource_type="student",
        resource=student,
        category=AuditCategory.STUDENT_RECORD,
    )
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    enforce_writable(decision, changes)
    updated = service.update_student(
        ctx.db, student=student, changes=changes, actor_id=ctx.principal.id
    )
    return StudentOut.model_validate(updated)


# ---------------------------------------------------------------------------
# Holds
# ---------------------------------------------------------------------------


class HoldIn(Schema):
    kind: Annotated[str, Field(max_length=40)]
    reason: Annotated[str, Field(min_length=5, max_length=500)]


@router.post("/{student_id}/holds", response_model=StudentOut)
def place_hold(student_id: uuid.UUID, payload: HoldIn, ctx: StaffContext) -> StudentOut:
    student = get_or_404(ctx, Student, student_id)
    authorize(
        engine=ctx.engine,
        action="student:place_hold",
        resource_type="student",
        resource=student,
        category=AuditCategory.STUDENT_RECORD,
    )
    return StudentOut.model_validate(
        service.place_hold(
            ctx.db,
            student=student,
            kind=payload.kind,
            reason=payload.reason,
            actor_id=ctx.principal.id,
        )
    )


@router.delete("/{student_id}/holds/{kind}", response_model=StudentOut)
def clear_hold(student_id: uuid.UUID, kind: str, payload: Reason, ctx: StaffContext) -> StudentOut:
    student = get_or_404(ctx, Student, student_id)
    authorize(
        engine=ctx.engine,
        action="student:clear_hold",
        resource_type="student",
        resource=student,
        category=AuditCategory.STUDENT_RECORD,
    )
    return StudentOut.model_validate(
        service.clear_hold(
            ctx.db, student=student, kind=kind, actor_id=ctx.principal.id, note=payload.reason
        )
    )


# ---------------------------------------------------------------------------
# Status changes
# ---------------------------------------------------------------------------


class StatusChangeIn(Schema):
    kind: str
    to_status: str
    effective_from: date
    effective_to: date | None = None
    reason: Annotated[str, Field(min_length=10, max_length=2000)]
    evidence_attachment_ids: list[uuid.UUID] = Field(default_factory=list)


class StatusChangeOut(Schema):
    id: uuid.UUID
    student_id: uuid.UUID
    kind: str
    from_status: str
    to_status: str
    effective_from: date
    effective_to: date | None
    reason: str
    status: str
    requested_by_id: uuid.UUID | None
    requested_at: datetime
    approved_by_id: uuid.UUID | None
    approved_at: datetime | None
    minute_reference: str | None


@router.post(
    "/{student_id}/status-changes",
    response_model=StatusChangeOut,
    status_code=status.HTTP_201_CREATED,
)
def request_status_change(
    student_id: uuid.UUID, payload: StatusChangeIn, ctx: AnyContext
) -> StatusChangeOut:
    student = get_or_404(ctx, Student, student_id)
    authorize(
        engine=ctx.engine,
        action="student_status_change:create",
        resource_type="student_status_change",
        resource={
            "id": None,
            "student_id": str(student.id),
            "kind": payload.kind,
            "status": "requested",
            "to_status": payload.to_status,
        },
        category=AuditCategory.STUDENT_RECORD,
    )
    return StatusChangeOut.model_validate(
        service.request_status_change(
            ctx.db,
            student=student,
            kind=payload.kind,
            to_status=payload.to_status,
            effective_from=payload.effective_from,
            effective_to=payload.effective_to,
            reason=payload.reason,
            evidence_attachment_ids=payload.evidence_attachment_ids,
            actor_id=ctx.principal.id,
        )
    )


class ApproveStatusChangeIn(Reason):
    minute_reference: str | None = None


@router.post("/status-changes/{change_id}/approve", response_model=StatusChangeOut)
def approve_status_change(
    change_id: uuid.UUID, payload: ApproveStatusChangeIn, ctx: StaffContext
) -> StatusChangeOut:
    change = get_or_404(ctx, StatusChange, change_id)
    authorize(
        engine=ctx.engine,
        action="student_status_change:approve",
        resource_type="student_status_change",
        resource=change,
        category=AuditCategory.STUDENT_RECORD,
    )
    return StatusChangeOut.model_validate(
        service.approve_status_change(
            ctx.db,
            change=change,
            actor_id=ctx.principal.id,
            minute_reference=payload.minute_reference,
        )
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class RegistrationCourseOut(Schema):
    id: uuid.UUID
    course_offering_id: uuid.UUID
    credit_units: int
    category: str
    is_retake: bool
    attempt_number: int
    is_audit: bool


class RegistrationOut(Schema):
    id: uuid.UUID
    student_id: uuid.UUID
    semester_id: uuid.UUID
    status: str
    total_credits: int
    retake_credits: int
    submitted_at: datetime | None
    approved_at: datetime | None
    is_late: bool
    exam_card_issued_at: datetime | None
    courses: list[RegistrationCourseOut] = Field(default_factory=list)


class RegistrationCoursesIn(Schema):
    course_offering_ids: Annotated[list[uuid.UUID], Field(max_length=20)]


class MyRegistrationCourseOut(RegistrationCourseOut):
    code: str = ""
    title: str = ""


class MyRegistrationOut(Schema):
    """A registration as the student needs to read it.

    Course offering ids are the right key and the wrong label. Resolved here
    because the alternative is the portal fetching a course per row, and a
    student on a full load has eight. Declared separately from
    `RegistrationOut` rather than subclassing it: narrowing an inherited list
    field is exactly the variance mistake mypy exists to catch.
    """

    id: uuid.UUID
    student_id: uuid.UUID
    semester_id: uuid.UUID
    semester_name: str | None = None
    status: str
    total_credits: int
    retake_credits: int
    submitted_at: datetime | None
    approved_at: datetime | None
    is_late: bool
    exam_card_issued_at: datetime | None
    courses: list[MyRegistrationCourseOut] = Field(default_factory=list)


@router.get("/me/registrations", response_model=list[MyRegistrationOut])
def my_registrations(ctx: StudentContext) -> list[MyRegistrationOut]:
    """Every registration this student has opened, newest first.

    Unpaginated on purpose: the list is one row per semester, so a student on
    the longest programme the institution runs has a dozen. Paginating it would
    cost a cursor and buy nothing.
    """
    from acmis.modules.curriculum.models import Course, CourseOffering
    from acmis.modules.shared.models import Semester

    authorize(
        engine=ctx.engine,
        action="registration:list",
        resource_type="registration",
        resource={"id": None, "student_id": str(ctx.student_id)},
        category=AuditCategory.ENROLMENT,
    )
    rows = ctx.db.scalars(
        select(Registration)
        .where(Registration.student_id == ctx.student_id)
        .order_by(Registration.created_at.desc())
    ).all()

    offering_ids = {course.course_offering_id for row in rows for course in row.courses}
    labels: dict[uuid.UUID, tuple[str, str]] = {}
    if offering_ids:
        for offering_id, code, title in ctx.db.execute(
            select(CourseOffering.id, Course.code, Course.title)
            .join(Course, Course.id == CourseOffering.course_id)
            .where(CourseOffering.id.in_(list(offering_ids)))
        ).all():
            labels[offering_id] = (str(code), str(title))

    semester_ids = {row.semester_id for row in rows}
    names: dict[uuid.UUID, str] = {}
    if semester_ids:
        for semester_id, name in ctx.db.execute(
            select(Semester.id, Semester.name).where(Semester.id.in_(list(semester_ids)))
        ).all():
            names[semester_id] = str(name)

    out: list[MyRegistrationOut] = []
    for row in rows:
        registration = MyRegistrationOut.model_validate(row)
        registration.semester_name = names.get(row.semester_id)
        for course in registration.courses:
            code, title = labels.get(course.course_offering_id, ("", ""))
            course.code = code
            course.title = title
        registration.courses.sort(key=lambda course: course.code)
        out.append(registration)
    return out


@router.post(
    "/{student_id}/registrations",
    response_model=RegistrationOut,
    status_code=status.HTTP_201_CREATED,
)
def open_registration(
    student_id: uuid.UUID, semester_id: uuid.UUID, ctx: AnyContext
) -> RegistrationOut:
    student = get_or_404(ctx, Student, student_id)
    authorize(
        engine=ctx.engine,
        action="registration:create",
        resource_type="registration",
        resource={"id": None, "student_id": str(student.id), "status": "draft"},
        category=AuditCategory.ENROLMENT,
    )
    return RegistrationOut.model_validate(
        service.create_registration(
            ctx.db, student=student, semester_id=semester_id, actor_id=ctx.principal.id
        )
    )


@router.put("/registrations/{registration_id}/courses", response_model=RegistrationOut)
def set_registration_courses(
    registration_id: uuid.UUID, payload: RegistrationCoursesIn, ctx: AnyContext
) -> RegistrationOut:
    registration = get_or_404(ctx, Registration, registration_id)
    authorize(
        engine=ctx.engine,
        action="registration:update",
        resource_type="registration",
        resource=registration,
        extra_attributes=service.registration_context(ctx.db, registration=registration),
        category=AuditCategory.ENROLMENT,
    )
    return RegistrationOut.model_validate(
        service.set_registration_courses(
            ctx.db,
            registration=registration,
            offering_ids=payload.course_offering_ids,
            actor_id=ctx.principal.id,
        )
    )


@router.post("/registrations/{registration_id}/submit", response_model=RegistrationOut)
def submit_registration(registration_id: uuid.UUID, ctx: AnyContext) -> RegistrationOut:
    """Submit a course registration.

    The window and fee-threshold attributes are supplied to the decision here
    rather than read from the row, because neither is a column — one comes from
    the semester's dates and the other from the student's ledger. That is what
    lets `students.registration-window` be a policy an institution can adjust
    rather than a hard-coded `if`.
    """
    registration = get_or_404(ctx, Registration, registration_id)
    authorize(
        engine=ctx.engine,
        action="registration:submit",
        resource_type="registration",
        resource=registration,
        extra_attributes=service.registration_context(ctx.db, registration=registration),
        category=AuditCategory.ENROLMENT,
    )
    return RegistrationOut.model_validate(
        service.submit_registration(ctx.db, registration=registration, actor_id=ctx.principal.id)
    )


# ---------------------------------------------------------------------------
# Clearance
# ---------------------------------------------------------------------------


class ClearanceOut(Schema):
    id: uuid.UUID
    student_id: uuid.UUID
    purpose: str
    office: str
    status: str
    obligation_note: str | None
    outstanding_amount_minor: int | None
    cleared_at: datetime | None


# ---------------------------------------------------------------------------
# The student's own timetable
# ---------------------------------------------------------------------------


class ClassSlotOut(Schema):
    course_offering_id: uuid.UUID
    code: str
    title: str
    #: 1 = Monday, to match ISO and the printed timetable.
    day_of_week: int
    starts_at: str
    ends_at: str
    session_kind: str
    room: str | None
    is_online: bool
    meeting_url: str | None


class ExamSittingOut(Schema):
    course_offering_id: uuid.UUID
    code: str
    title: str
    sitting_date: date
    starts_at: str
    duration_minutes: int
    session: str
    rooms: list[str]
    status: str


class MyTimetableOut(Schema):
    semester_id: uuid.UUID | None
    semester_name: str | None
    classes: list[ClassSlotOut]
    exams: list[ExamSittingOut]


@router.get("/me/timetable", response_model=MyTimetableOut)
def my_timetable(ctx: StudentContext) -> MyTimetableOut:
    """The classes and examinations for the courses this student registered for.

    Driven off the registration rather than off the programme, because those
    differ the moment a student retakes a course or drops one: a timetable
    built from the curriculum shows a class the student is not entitled to sit
    and omits the retake they must.
    """
    from acmis.modules.assessment.models import ExamSitting
    from acmis.modules.curriculum.models import Course, CourseOffering, TimetableSlot
    from acmis.modules.shared.models import Building, Room, Semester

    authorize(
        engine=ctx.engine,
        action="timetable:read",
        resource_type="timetable_slot",
        resource={
            "id": None,
            "student_id": str(ctx.student_id),
            "offering_id": None,
            "room_id": None,
            "staff_id": None,
        },
        category=AuditCategory.ENROLMENT,
    )

    semester = ctx.db.scalars(
        select(Semester)
        .where(Semester.is_current.is_(True))
        .order_by(Semester.starts_on.desc())
        .limit(1)
    ).first()
    if semester is None:
        return MyTimetableOut(semester_id=None, semester_name=None, classes=[], exams=[])

    registration = ctx.db.scalars(
        select(Registration)
        .where(
            Registration.student_id == ctx.student_id,
            Registration.semester_id == semester.id,
        )
        .order_by(Registration.created_at.desc())
        .limit(1)
    ).first()
    offering_ids = (
        [
            course.course_offering_id
            for course in registration.courses
            if course.dropped_at is None and course.withdrawn_at is None
        ]
        if registration is not None
        else []
    )
    if not offering_ids:
        return MyTimetableOut(
            semester_id=semester.id, semester_name=semester.name, classes=[], exams=[]
        )

    labels: dict[uuid.UUID, tuple[str, str]] = {
        offering_id: (str(code), str(title))
        for offering_id, code, title in ctx.db.execute(
            select(CourseOffering.id, Course.code, Course.title)
            .join(Course, Course.id == CourseOffering.course_id)
            .where(CourseOffering.id.in_(offering_ids))
        ).all()
    }

    # Room names are resolved once for both lists: an exam sitting names its
    # halls and a class names its room, and neither is readable as a UUID.
    room_names: dict[uuid.UUID, str] = {
        room_id: f"{building_code} {room_code}"
        for room_id, room_code, building_code in ctx.db.execute(
            select(Room.id, Room.code, Building.code).join(
                Building, Building.id == Room.building_id
            )
        ).all()
    }

    classes = [
        ClassSlotOut(
            course_offering_id=slot.offering_id,
            code=labels.get(slot.offering_id, ("", ""))[0],
            title=labels.get(slot.offering_id, ("", ""))[1],
            day_of_week=slot.day_of_week,
            starts_at=slot.starts_at,
            ends_at=slot.ends_at,
            session_kind=slot.session_kind,
            room=room_names.get(slot.room_id) if slot.room_id else None,
            is_online=slot.is_online,
            meeting_url=slot.meeting_url,
        )
        for slot in ctx.db.scalars(
            select(TimetableSlot)
            .where(
                TimetableSlot.offering_id.in_(offering_ids),
                TimetableSlot.deleted_at.is_(None),
            )
            .order_by(TimetableSlot.day_of_week, TimetableSlot.starts_at)
        ).all()
    ]

    exams = [
        ExamSittingOut(
            course_offering_id=sitting.course_offering_id,
            code=labels.get(sitting.course_offering_id, ("", ""))[0],
            title=labels.get(sitting.course_offering_id, ("", ""))[1],
            sitting_date=sitting.sitting_date,
            starts_at=sitting.starts_at,
            duration_minutes=sitting.duration_minutes,
            session=sitting.session,
            rooms=[room_names[r] for r in sitting.room_ids if r in room_names],
            status=sitting.status,
        )
        for sitting in ctx.db.scalars(
            select(ExamSitting)
            .where(
                ExamSitting.course_offering_id.in_(offering_ids),
                ExamSitting.semester_id == semester.id,
                ExamSitting.deleted_at.is_(None),
            )
            .order_by(ExamSitting.sitting_date, ExamSitting.starts_at)
        ).all()
    ]

    return MyTimetableOut(
        semester_id=semester.id,
        semester_name=semester.name,
        classes=classes,
        exams=exams,
    )


@router.get("/{student_id}/clearance", response_model=list[ClearanceOut])
def get_clearance(
    student_id: uuid.UUID, ctx: AnyContext, purpose: str = "graduation"
) -> list[ClearanceOut]:
    student = get_or_404(ctx, Student, student_id)
    authorize(
        engine=ctx.engine,
        action="clearance:read",
        resource_type="clearance",
        resource={"id": None, "student_id": str(student.id), "purpose": purpose},
    )
    rows = (
        ctx.db.execute(
            select(Clearance).where(
                Clearance.student_id == student_id,
                Clearance.purpose == purpose,
                Clearance.deleted_at.is_(None),
            )
        )
        .scalars()
        .all()
    )
    return [ClearanceOut.model_validate(r) for r in rows]
