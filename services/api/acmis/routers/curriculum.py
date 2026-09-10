"""Course planning and curriculum management endpoints."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query, status
from pydantic import Field
from sqlalchemy import select

from acmis.core.abac import authorize
from acmis.core.audit import AuditCategory, diff, emit
from acmis.core.deps import AnyContext, PageQuery, StaffContext
from acmis.core.errors import Conflict, RuleViolation
from acmis.core.models import utcnow
from acmis.core.pagination import keyset_page
from acmis.core.schemas import Page, Reason, Schema
from acmis.modules.curriculum.models import (
    ApprovalStatus,
    Course,
    CourseOffering,
    CurriculumCourse,
    CurriculumVersion,
    Programme,
    TeachingAllocation,
    TimetableSlot,
)
from acmis.routers._common import get_or_404

router = APIRouter(prefix="/curriculum", tags=["curriculum"])


class ProgrammeOut(Schema):
    id: uuid.UUID
    code: str
    name: str
    short_name: str | None
    award_title: str
    award_abbreviation: str
    award_level: str
    owning_unit_id: uuid.UUID
    duration_semesters: int
    delivery_modes: list[str]
    study_level: str
    accreditation_number: str | None
    accredited_until: date | None
    status: str
    is_active: bool


class ProgrammeIn(Schema):
    code: Annotated[str, Field(max_length=30)]
    name: Annotated[str, Field(max_length=300)]
    short_name: str | None = None
    award_title: Annotated[str, Field(max_length=300)]
    award_abbreviation: Annotated[str, Field(max_length=30)]
    award_level: str
    owning_unit_id: uuid.UUID
    duration_semesters: Annotated[int, Field(ge=1, le=24)]
    delivery_modes: list[str] = Field(default_factory=lambda: ["full_time"])
    study_level: str = "undergraduate"
    description: str | None = None
    entry_requirements: str | None = None
    accreditation_number: str | None = None
    accredited_until: date | None = None
    nqf_level: int | None = None


@router.get("/programmes", response_model=Page[ProgrammeOut])
def list_programmes(
    ctx: AnyContext,
    page: PageQuery,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    unit_id: uuid.UUID | None = None,
    active_only: bool = True,
) -> Page[ProgrammeOut]:
    authorize(
        engine=ctx.engine,
        action="programme:list",
        resource_type="programme",
        resource={"id": None, "status": status_filter or "approved"},
    )
    stmt = select(Programme).where(Programme.deleted_at.is_(None))
    if status_filter:
        stmt = stmt.where(Programme.status == status_filter)
    if active_only:
        stmt = stmt.where(Programme.is_active.is_(True))
    if unit_id:
        stmt = stmt.where(Programme.owning_unit_id == unit_id)
    found = keyset_page(ctx.db, stmt, page=page, key=Programme.code, ident=Programme.id)
    return Page.of(
        [ProgrammeOut.model_validate(r) for r in found.rows],
        limit=page.limit,
        next_cursor=found.next_cursor,
        total=found.total,
    )


@router.post("/programmes", response_model=ProgrammeOut, status_code=status.HTTP_201_CREATED)
def create_programme(payload: ProgrammeIn, ctx: StaffContext) -> ProgrammeOut:
    """Draft a programme. Owned by a department, approved by Senate later.

    The unit ancestry is denormalised onto the row here, because every
    unit-scoped policy compares against `faculty_ids`/`department_ids` and a
    recursive join per authorization decision is not affordable.
    """
    from acmis.modules.shared.models import AcademicUnit

    unit = get_or_404(ctx, AcademicUnit, payload.owning_unit_id)
    authorize(
        engine=ctx.engine,
        action="programme:create",
        resource_type="programme",
        resource={
            "id": None,
            "status": "draft",
            "department_ids": [str(unit.id)],
            "faculty_ids": [str(a) for a in (unit.ancestor_ids or ())],
        },
        category=AuditCategory.CURRICULUM,
    )
    ancestry = list(unit.ancestor_ids or ())
    programme = Programme(
        **payload.model_dump(),
        faculty_ids=ancestry,
        department_ids=[unit.id],
        status=ApprovalStatus.DRAFT,
        created_by_id=ctx.principal.id,
    )
    ctx.db.add(programme)
    ctx.db.flush()
    emit(
        "programme:create",
        AuditCategory.CURRICULUM,
        resource_type="programme",
        resource_id=programme.id,
        resource_label=f"{programme.code} — {programme.name}",
        summary=f"Drafted programme {programme.code}",
    )
    return ProgrammeOut.model_validate(programme)


class CurriculumVersionOut(Schema):
    id: uuid.UUID
    programme_id: uuid.UUID
    version_label: str
    cohort_from: str
    cohort_to: str | None
    total_credit_units: int
    min_credits_per_semester: int
    max_credits_per_semester: int
    max_credits_with_retakes: int
    progression_rules: dict[str, Any]
    classification_rules: dict[str, Any]
    status: str
    approved_at: datetime | None
    senate_minute_reference: str | None


class CurriculumVersionIn(Schema):
    programme_id: uuid.UUID
    version_label: Annotated[str, Field(max_length=30)]
    cohort_from: Annotated[str, Field(max_length=20)]
    cohort_to: str | None = None
    total_credit_units: int = 0
    min_credits_per_semester: int = 15
    max_credits_per_semester: int = 24
    max_credits_with_retakes: int = 27
    progression_rules: dict[str, Any] = Field(default_factory=dict)
    classification_rules: dict[str, Any] = Field(default_factory=dict)
    learning_outcomes: list[str] = Field(default_factory=list)


@router.post("/versions", response_model=CurriculumVersionOut, status_code=status.HTTP_201_CREATED)
def create_version(payload: CurriculumVersionIn, ctx: StaffContext) -> CurriculumVersionOut:
    programme = get_or_404(ctx, Programme, payload.programme_id)
    authorize(
        engine=ctx.engine,
        action="curriculum_version:create",
        resource_type="curriculum_version",
        resource={
            "id": None,
            "programme_id": str(programme.id),
            "status": "draft",
            "faculty_ids": [str(f) for f in programme.faculty_ids],
            "department_ids": [str(d) for d in programme.department_ids],
        },
        category=AuditCategory.CURRICULUM,
    )
    version = CurriculumVersion(
        **payload.model_dump(), status=ApprovalStatus.DRAFT, created_by_id=ctx.principal.id
    )
    ctx.db.add(version)
    ctx.db.flush()
    emit(
        "curriculum_version:create",
        AuditCategory.CURRICULUM,
        resource_type="curriculum_version",
        resource_id=version.id,
        resource_label=f"{programme.code} {version.version_label}",
        summary=f"Drafted curriculum version {version.version_label} for {programme.code}",
    )
    return CurriculumVersionOut.model_validate(version)


class TransitionIn(Reason):
    minute_reference: str | None = None


@router.post("/versions/{version_id}/{action}", response_model=CurriculumVersionOut)
def transition_version(
    version_id: uuid.UUID,
    action: str,
    payload: TransitionIn,
    ctx: StaffContext,
) -> CurriculumVersionOut:
    """Move a curriculum version along the approval chain.

    Department drafts, faculty board recommends, Senate approves — three
    grants, three people. The whole value of the chain is that the person who
    wrote the programme is not the person who approved it, so the submitter is
    refused at the approval step even if their permissions would otherwise
    allow it.
    """
    transitions: dict[str, tuple[set[str], str]] = {
        "submit": ({ApprovalStatus.DRAFT, ApprovalStatus.RETURNED}, ApprovalStatus.SUBMITTED),
        "recommend": ({ApprovalStatus.SUBMITTED}, ApprovalStatus.RECOMMENDED),
        "approve": ({ApprovalStatus.RECOMMENDED}, ApprovalStatus.APPROVED),
        "reject": (
            {ApprovalStatus.SUBMITTED, ApprovalStatus.RECOMMENDED},
            ApprovalStatus.REJECTED,
        ),
        "return": (
            {ApprovalStatus.SUBMITTED, ApprovalStatus.RECOMMENDED},
            ApprovalStatus.RETURNED,
        ),
    }
    if action not in transitions:
        raise RuleViolation(f"'{action}' is not a curriculum transition.")

    version = get_or_404(ctx, CurriculumVersion, version_id)
    authorize(
        engine=ctx.engine,
        action=f"curriculum_version:{action}",
        resource_type="curriculum_version",
        resource=version,
        category=AuditCategory.CURRICULUM,
    )

    from_states, to_state = transitions[action]
    if version.status not in from_states:
        raise Conflict(f"A {version.status} version cannot be {action}ed.")
    if action == "approve" and version.submitted_by_id == ctx.principal.id:
        raise RuleViolation(
            "A curriculum cannot be approved by the person who submitted it.",
            rule="separation_of_duties",
        )
    if action == "approve" and not version.structure:
        raise RuleViolation(
            "A curriculum version with no courses cannot be approved.",
            rule="empty_curriculum",
        )

    before = {"status": version.status}
    version.status = to_state
    now = utcnow()
    if action == "submit":
        version.submitted_by_id = ctx.principal.id
        version.submitted_at = now
    elif action == "recommend":
        version.recommended_by_id = ctx.principal.id
        version.recommended_at = now
    elif action == "approve":
        version.approved_by_id = ctx.principal.id
        version.approved_at = now
        version.senate_minute_reference = payload.minute_reference
    elif action in {"return", "reject"}:
        version.return_comments = payload.reason
    ctx.db.flush()

    emit(
        f"curriculum_version:{action}",
        AuditCategory.CURRICULUM,
        resource_type="curriculum_version",
        resource_id=version.id,
        summary=f"{before['status']} -> {version.status}",
        changes=diff(before, {"status": version.status}),
        metadata={"reason": payload.reason, "minute_reference": payload.minute_reference},
        severity="notice",
    )
    return CurriculumVersionOut.model_validate(version)


class CourseOut(Schema):
    id: uuid.UUID
    code: str
    title: str
    owning_unit_id: uuid.UUID
    credit_units: int
    lecture_hours: int
    tutorial_hours: int
    practical_hours: int
    level: int
    assessment_mode: str
    counts_toward_gpa: bool
    status: str
    is_active: bool


class CourseIn(Schema):
    code: Annotated[str, Field(max_length=20)]
    title: Annotated[str, Field(max_length=300)]
    owning_unit_id: uuid.UUID
    credit_units: Annotated[int, Field(ge=1, le=30)]
    lecture_hours: int = 0
    tutorial_hours: int = 0
    practical_hours: int = 0
    field_hours: int = 0
    level: int = 1
    description: str | None = None
    learning_outcomes: list[str] = Field(default_factory=list)
    assessment_mode: str = "written_exam"
    counts_toward_gpa: bool = True


@router.post("/courses", response_model=CourseOut, status_code=status.HTTP_201_CREATED)
def create_course(payload: CourseIn, ctx: StaffContext) -> CourseOut:
    """Create a course, checking the declared credit weight against the hours.

    The NCHE credit-unit definition is arithmetic over contact hours — 15
    lecture hours, or 30 tutorial, or 45 practical, per unit. A course claiming
    4 units with 15 lecture hours is a data-entry error that later inflates
    every affected student's GPA weighting, so it is caught here rather than
    discovered in an accreditation audit.
    """
    from acmis.modules.shared.models import AcademicUnit

    unit = get_or_404(ctx, AcademicUnit, payload.owning_unit_id)
    authorize(
        engine=ctx.engine,
        action="course:create",
        resource_type="course",
        resource={
            "id": None,
            "status": "draft",
            "department_ids": [str(unit.id)],
            "faculty_ids": [str(a) for a in (unit.ancestor_ids or ())],
        },
        category=AuditCategory.CURRICULUM,
    )

    notional = (
        payload.lecture_hours
        + payload.tutorial_hours / 2
        + payload.practical_hours / 3
        + payload.field_hours / 5
    )
    implied = notional / 15 if notional else 0
    if implied and abs(implied - payload.credit_units) > 0.75:
        raise RuleViolation(
            f"The contact hours imply about {implied:.1f} credit units, not "
            f"{payload.credit_units}.",
            rule="credit_hours_mismatch",
            details={"implied_credit_units": round(implied, 2)},
            waivable_by=["curriculum:approve"],
        )

    course = Course(
        **payload.model_dump(),
        faculty_ids=list(unit.ancestor_ids or ()),
        department_ids=[unit.id],
        status=ApprovalStatus.DRAFT,
        created_by_id=ctx.principal.id,
    )
    ctx.db.add(course)
    ctx.db.flush()
    emit(
        "course:create",
        AuditCategory.CURRICULUM,
        resource_type="course",
        resource_id=course.id,
        resource_label=f"{course.code} — {course.title}",
        summary=f"Created course {course.code} ({course.credit_units} CU)",
    )
    return CourseOut.model_validate(course)


@router.get("/courses", response_model=Page[CourseOut])
def list_courses(
    ctx: AnyContext,
    page: PageQuery,
    unit_id: uuid.UUID | None = None,
    level: int | None = None,
    search: Annotated[str | None, Query(max_length=80)] = None,
) -> Page[CourseOut]:
    authorize(
        engine=ctx.engine,
        action="course:list",
        resource_type="course",
        resource={"id": None, "status": "approved"},
    )
    from sqlalchemy import func as sqlfunc

    stmt = select(Course).where(Course.deleted_at.is_(None), Course.is_active.is_(True))
    if unit_id:
        stmt = stmt.where(Course.owning_unit_id == unit_id)
    if level:
        stmt = stmt.where(Course.level == level)
    if search:
        term = f"%{search.lower()}%"
        stmt = stmt.where(
            sqlfunc.lower(Course.code).like(term) | sqlfunc.lower(Course.title).like(term)
        )
    found = keyset_page(ctx.db, stmt, page=page, key=Course.code, ident=Course.id)
    return Page.of(
        [CourseOut.model_validate(r) for r in found.rows],
        limit=page.limit,
        next_cursor=found.next_cursor,
        total=found.total,
    )


class CurriculumCourseIn(Schema):
    course_id: uuid.UUID
    year_of_study: Annotated[int, Field(ge=1, le=12)]
    semester_kind: str
    category: str = "core"
    credit_units_override: int | None = None
    elective_group: str | None = None
    elective_group_choose: int | None = None
    is_required_for_progression: bool = True


@router.post("/versions/{version_id}/courses", response_model=dict)
def add_curriculum_course(
    version_id: uuid.UUID, payload: CurriculumCourseIn, ctx: StaffContext
) -> dict[str, Any]:
    version = get_or_404(ctx, CurriculumVersion, version_id)
    authorize(
        engine=ctx.engine,
        action="curriculum_version:update",
        resource_type="curriculum_version",
        resource=version,
        category=AuditCategory.CURRICULUM,
    )
    if version.status == ApprovalStatus.APPROVED:
        # An approved version is frozen: changing a credit weight a cohort has
        # already been assessed under retroactively changes their CGPA.
        raise Conflict("An approved curriculum version cannot be changed. Create a new version.")

    course = get_or_404(ctx, Course, payload.course_id)
    row = CurriculumCourse(
        version_id=version.id, **payload.model_dump(), created_by_id=ctx.principal.id
    )
    ctx.db.add(row)
    ctx.db.flush()

    total = sum((c.credit_units_override or c.course.credit_units) for c in version.structure)
    version.total_credit_units = total
    emit(
        "curriculum_version:update",
        AuditCategory.CURRICULUM,
        resource_type="curriculum_version",
        resource_id=version.id,
        summary=f"Added {course.code} to year {payload.year_of_study}",
        metadata={"course_code": course.code, "total_credit_units": total},
    )
    return {"id": str(row.id), "total_credit_units": total}


class OfferingOut(Schema):
    id: uuid.UUID
    course_id: uuid.UUID
    semester_id: uuid.UUID
    campus_id: uuid.UUID | None
    group_code: str | None
    delivery_mode: str
    capacity: int | None
    registered_count: int
    is_open: bool
    mark_sheet_generated_at: datetime | None


class OfferingIn(Schema):
    course_id: uuid.UUID
    semester_id: uuid.UUID
    campus_id: uuid.UUID | None = None
    group_code: str | None = None
    delivery_mode: str = "full_time"
    assessment_scheme_id: uuid.UUID | None = None
    capacity: int | None = None


@router.post("/offerings", response_model=OfferingOut, status_code=status.HTTP_201_CREATED)
def create_offering(payload: OfferingIn, ctx: StaffContext) -> OfferingOut:
    course = get_or_404(ctx, Course, payload.course_id)
    authorize(
        engine=ctx.engine,
        action="course_offering:create",
        resource_type="course_offering",
        resource={
            "id": None,
            "course_id": str(course.id),
            "semester_id": str(payload.semester_id),
            "faculty_ids": [str(f) for f in course.faculty_ids],
            "department_ids": [str(d) for d in course.department_ids],
            "status": "approved",
        },
        category=AuditCategory.CURRICULUM,
    )
    offering = CourseOffering(
        **payload.model_dump(),
        faculty_ids=list(course.faculty_ids or ()),
        department_ids=list(course.department_ids or ()),
        created_by_id=ctx.principal.id,
    )
    ctx.db.add(offering)
    ctx.db.flush()
    emit(
        "course_offering:create",
        AuditCategory.CURRICULUM,
        resource_type="course_offering",
        resource_id=offering.id,
        resource_label=f"{course.code} offering",
        summary=f"Opened {course.code} for the semester",
    )
    return OfferingOut.model_validate(offering)


class AllocationIn(Schema):
    staff_id: uuid.UUID
    role: str = "lecturer"
    contact_hours: float | None = None
    load_share_percent: float | None = None
    can_enter_marks: bool = True
    starts_on: date | None = None
    ends_on: date | None = None


@router.post("/offerings/{offering_id}/allocations", response_model=dict)
def allocate_teaching(
    offering_id: uuid.UUID, payload: AllocationIn, ctx: StaffContext
) -> dict[str, Any]:
    """Assign a member of staff to teach an offering.

    This is what confers mark-entry authority: `assessment.mark-entry` grants
    it to the staff assigned here and to nobody else, and the date bounds are
    what revoke it when a part-time contract ends. An external examiner is
    allocated with `can_enter_marks=False` — they moderate, they do not enter.
    """
    offering = get_or_404(ctx, CourseOffering, offering_id)
    authorize(
        engine=ctx.engine,
        action="course_offering:allocate",
        resource_type="course_offering",
        resource=offering,
        category=AuditCategory.CURRICULUM,
    )
    if payload.role == "external_examiner" and payload.can_enter_marks:
        raise RuleViolation(
            "An external examiner moderates rather than enters marks.",
            rule="external_examiner_cannot_enter",
        )

    allocation = TeachingAllocation(
        offering_id=offering.id,
        **payload.model_dump(),
        allocated_by_id=ctx.principal.id,
        created_by_id=ctx.principal.id,
    )
    ctx.db.add(allocation)
    ctx.db.flush()
    emit(
        "teaching_allocation:create",
        AuditCategory.CURRICULUM,
        resource_type="course_offering",
        resource_id=offering.id,
        summary=f"Allocated staff {payload.staff_id} as {payload.role}",
        metadata={
            "can_enter_marks": payload.can_enter_marks,
            "ends_on": payload.ends_on.isoformat() if payload.ends_on else None,
        },
        severity="notice",
    )
    return {"id": str(allocation.id)}


class TimetableSlotIn(Schema):
    offering_id: uuid.UUID
    room_id: uuid.UUID | None = None
    staff_id: uuid.UUID | None = None
    day_of_week: Annotated[int, Field(ge=1, le=7)]
    starts_at: Annotated[str, Field(pattern=r"^\d{2}:\d{2}$")]
    ends_at: Annotated[str, Field(pattern=r"^\d{2}:\d{2}$")]
    session_kind: str = "lecture"
    week_pattern: list[int] = Field(default_factory=list)
    is_online: bool = False


@router.post("/timetable", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_timetable_slot(payload: TimetableSlotIn, ctx: StaffContext) -> dict[str, Any]:
    """Schedule a session, reporting every kind of clash it causes.

    Three kinds, and they are genuinely different: a room double-booked, a
    lecturer in two places, and a cohort with two required courses at once.
    The last is the one students complain about and the one a unique index
    cannot see, so all three are checked and reported together rather than
    failing on the first.
    """
    offering = get_or_404(ctx, CourseOffering, payload.offering_id)
    authorize(
        engine=ctx.engine,
        action="timetable_slot:create",
        resource_type="timetable_slot",
        resource={
            "id": None,
            "offering_id": str(offering.id),
            "room_id": str(payload.room_id) if payload.room_id else None,
            "staff_id": str(payload.staff_id) if payload.staff_id else None,
        },
        category=AuditCategory.CURRICULUM,
    )

    clashes = _find_clashes(ctx, payload)
    if clashes:
        raise RuleViolation(
            "This slot clashes with existing sessions.",
            rule="timetable_clash",
            details={"clashes": clashes},
            waivable_by=["timetable:override_clash"],
        )

    slot = TimetableSlot(**payload.model_dump(), created_by_id=ctx.principal.id)
    ctx.db.add(slot)
    ctx.db.flush()
    emit(
        "timetable_slot:create",
        AuditCategory.CURRICULUM,
        resource_type="timetable_slot",
        resource_id=slot.id,
        summary=f"Scheduled day {payload.day_of_week} {payload.starts_at}-{payload.ends_at}",
    )
    return {"id": str(slot.id)}


def _find_clashes(ctx: StaffContext, payload: TimetableSlotIn) -> list[dict[str, Any]]:
    existing = (
        ctx.db.execute(
            select(TimetableSlot).where(
                TimetableSlot.day_of_week == payload.day_of_week,
                TimetableSlot.deleted_at.is_(None),
            )
        )
        .scalars()
        .all()
    )

    def overlaps(a_start: str, a_end: str, b_start: str, b_end: str) -> bool:
        return a_start < b_end and b_start < a_end

    clashes: list[dict[str, Any]] = []
    for slot in existing:
        if not overlaps(payload.starts_at, payload.ends_at, slot.starts_at, slot.ends_at):
            continue
        if payload.room_id and slot.room_id == payload.room_id:
            clashes.append({"kind": "room", "slot_id": str(slot.id)})
        if payload.staff_id and slot.staff_id == payload.staff_id:
            clashes.append({"kind": "staff", "slot_id": str(slot.id)})
        if slot.offering_id == payload.offering_id:
            clashes.append({"kind": "same_offering", "slot_id": str(slot.id)})
    return clashes
