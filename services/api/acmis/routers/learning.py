"""Teaching, learning materials and online assessment endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Request, status
from pydantic import Field
from sqlalchemy import func, select

from acmis.core.abac import authorize
from acmis.core.audit import AuditCategory
from acmis.core.deps import AnyContext, PageQuery, StaffContext, StudentContext
from acmis.core.errors import Conflict, NotFound
from acmis.core.pagination import keyset_page
from acmis.core.schemas import Page, RecordEnvelope, Schema
from acmis.modules.learning import service
from acmis.modules.learning.models import (
    Assignment,
    Attempt,
    AttemptResponse,
    CourseSpace,
    Material,
    OnlineAssessment,
    Question,
    QuestionBank,
    Submission,
)
from acmis.routers._common import get_or_404

router = APIRouter(prefix="/learning", tags=["learning"])


# ---------------------------------------------------------------------------
# Course spaces and materials
# ---------------------------------------------------------------------------


class SpaceOut(Schema):
    id: uuid.UUID
    course_offering_id: uuid.UUID
    semester_id: uuid.UUID
    welcome_message: str | None
    syllabus_outline: list[dict[str, Any]]
    is_published: bool
    published_at: datetime | None
    archived_at: datetime | None


class MaterialOut(Schema):
    id: uuid.UUID
    space_id: uuid.UUID
    kind: str
    title: str
    description: str | None
    week_number: int | None
    topic: str | None
    sequence: int
    attachment_id: uuid.UUID | None
    external_url: str | None
    duration_seconds: int | None
    is_published: bool
    available_from: datetime | None
    available_until: datetime | None
    allow_download: bool
    view_count: int
    unique_viewer_count: int


class MaterialIn(Schema):
    kind: str
    title: Annotated[str, Field(max_length=300)]
    description: str | None = None
    week_number: Annotated[int | None, Field(ge=1, le=60)] = None
    topic: str | None = None
    sequence: int = 0
    attachment_id: uuid.UUID | None = None
    external_url: Annotated[str | None, Field(max_length=1000)] = None
    duration_seconds: int | None = None
    is_published: bool = False
    available_from: datetime | None = None
    available_until: datetime | None = None
    allow_download: bool = True
    requires_fee_clearance: bool = False


@router.post("/spaces", response_model=SpaceOut, status_code=status.HTTP_201_CREATED)
def open_space(course_offering_id: uuid.UUID, ctx: StaffContext) -> SpaceOut:
    from acmis.modules.curriculum.models import CourseOffering

    offering = get_or_404(ctx, CourseOffering, course_offering_id)
    authorize(
        engine=ctx.engine,
        action="course_space:create",
        resource_type="course_space",
        resource={
            "id": None,
            "course_offering_id": str(offering.id),
            "department_ids": [str(d) for d in offering.department_ids],
            "faculty_ids": [str(f) for f in offering.faculty_ids],
            "is_published": False,
        },
        category=AuditCategory.CURRICULUM,
    )
    return SpaceOut.model_validate(
        service.ensure_space(
            ctx.db, course_offering_id=course_offering_id, actor_id=ctx.principal.id
        )
    )


@router.post(
    "/spaces/{space_id}/materials",
    response_model=MaterialOut,
    status_code=status.HTTP_201_CREATED,
)
def publish_material(space_id: uuid.UUID, payload: MaterialIn, ctx: StaffContext) -> MaterialOut:
    space = get_or_404(ctx, CourseSpace, space_id)
    authorize(
        engine=ctx.engine,
        action="material:create",
        resource_type="material",
        resource={
            "id": None,
            "space_id": str(space.id),
            "course_offering_id": str(space.course_offering_id),
            "kind": payload.kind,
            "is_published": payload.is_published,
            "department_ids": [str(d) for d in space.department_ids],
            "faculty_ids": [str(f) for f in space.faculty_ids],
        },
        category=AuditCategory.CURRICULUM,
    )
    return MaterialOut.model_validate(
        service.publish_material(
            ctx.db, space=space, payload=payload.model_dump(), actor_id=ctx.principal.id
        )
    )


@router.get("/spaces/{space_id}/materials", response_model=list[MaterialOut])
def list_materials(space_id: uuid.UUID, ctx: AnyContext) -> list[MaterialOut]:
    """Material in a course space.

    A student sees only what is published and in its availability window; a
    lecturer sees everything, including what they are still preparing. The
    difference is the `is_available`/`is_registered` attributes handed to the
    decision — the policy decides, and the query then filters to match so an
    unpublished item never even leaves the database for a student.
    """
    space = get_or_404(ctx, CourseSpace, space_id)
    is_student = ctx.principal.kind == "student"
    registered = service_is_registered(ctx, space.course_offering_id) if is_student else True

    authorize(
        engine=ctx.engine,
        action="material:list",
        resource_type="material",
        resource={
            "id": None,
            "space_id": str(space.id),
            "course_offering_id": str(space.course_offering_id),
            "is_registered": registered,
            "is_available": True,
            "is_published": True,
            "department_ids": [str(d) for d in space.department_ids],
            "faculty_ids": [str(f) for f in space.faculty_ids],
        },
        category=AuditCategory.CURRICULUM,
    )

    rows = (
        ctx.db.execute(
            select(Material)
            .where(Material.space_id == space_id, Material.deleted_at.is_(None))
            .order_by(Material.week_number.asc().nullslast(), Material.sequence)
        )
        .scalars()
        .all()
    )
    if is_student:
        rows = [m for m in rows if m.is_available]
    return [MaterialOut.model_validate(m) for m in rows]


def service_is_registered(ctx: AnyContext, course_offering_id: uuid.UUID) -> bool:
    from acmis.modules.students.models import RegistrationCourse

    if not ctx.student_id:
        return False
    count: int = int(
        ctx.db.execute(
            select(func.count())
            .select_from(RegistrationCourse)
            .where(
                RegistrationCourse.student_id == ctx.student_id,
                RegistrationCourse.course_offering_id == course_offering_id,
                RegistrationCourse.dropped_at.is_(None),
                RegistrationCourse.deleted_at.is_(None),
            )
        ).scalar_one()
    )
    return count > 0


class ViewIn(Schema):
    seconds: Annotated[int, Field(ge=0, le=86400)] = 0
    downloaded: bool = False
    completion_percent: Annotated[int | None, Field(ge=0, le=100)] = None


@router.post("/materials/{material_id}/view", status_code=status.HTTP_204_NO_CONTENT)
def record_view(material_id: uuid.UUID, ctx: StudentContext, payload: ViewIn | None = None) -> None:
    """Record that a student opened a material.

    Not audited. A student reading their own course notes is not an access to
    anyone's record, and putting millions of page views into the audit trail
    would bury the accesses that matter.
    """
    body = payload or ViewIn()
    material = get_or_404(ctx, Material, material_id)
    space = ctx.db.get(CourseSpace, material.space_id)
    authorize(
        engine=ctx.engine,
        action="material:read",
        resource_type="material",
        resource={
            "id": str(material.id),
            "course_offering_id": str(space.course_offering_id) if space else None,
            "is_registered": service_is_registered(
                ctx, space.course_offering_id if space else uuid.UUID(int=0)
            ),
            "is_available": material.is_available,
            "is_published": material.is_published,
        },
    )
    service.record_material_view(
        ctx.db,
        material=material,
        student_id=ctx.student_id,
        seconds=body.seconds,
        downloaded=body.downloaded,
        completion_percent=body.completion_percent,
    )


# ---------------------------------------------------------------------------
# Question banks
# ---------------------------------------------------------------------------


class QuestionOptionIn(Schema):
    label: str | None = None
    body: str
    is_correct: bool = False
    feedback: str | None = None
    pin_position: bool = False


class QuestionIn(Schema):
    kind: str
    stem: str
    marks: Annotated[float, Field(gt=0, le=1000)] = 1
    negative_marks: Annotated[float, Field(ge=0)] = 0
    answer_key: dict[str, Any] = Field(default_factory=dict)
    variable_sets: list[dict[str, Any]] = Field(default_factory=list)
    explanation: str | None = None
    rubric: list[dict[str, Any]] = Field(default_factory=list)
    learning_outcome: str | None = None
    topic: str | None = None
    cognitive_level: str | None = None
    difficulty: str = "medium"
    options: list[QuestionOptionIn] = Field(default_factory=list)


class QuestionOut(Schema):
    id: uuid.UUID
    bank_id: uuid.UUID
    kind: str
    stem: str
    marks: float
    negative_marks: float
    topic: str | None
    cognitive_level: str | None
    difficulty: str
    learning_outcome: str | None
    times_used: int
    times_answered: int
    facility_index: float | None
    discrimination_index: float | None
    revision: int
    is_locked: bool
    is_active: bool
    #: Masked for anyone who may not see it, and never returned to a student —
    #: `learning.answer-key-confidentiality` refuses that outright.
    answer_key: dict[str, Any] | None = None
    explanation: str | None = None
    rubric: list[dict[str, Any]] | None = None


class BankIn(Schema):
    code: Annotated[str, Field(max_length=40)]
    name: Annotated[str, Field(max_length=200)]
    description: str | None = None
    course_id: uuid.UUID | None = None
    owning_unit_id: uuid.UUID | None = None
    is_shared: bool = False


class BankOut(Schema):
    id: uuid.UUID
    code: str
    name: str
    description: str | None
    course_id: uuid.UUID | None
    owning_unit_id: uuid.UUID | None
    is_shared: bool
    question_count: int


@router.post("/banks", response_model=BankOut, status_code=status.HTTP_201_CREATED)
def create_bank(payload: BankIn, ctx: StaffContext) -> BankOut:
    """Create a question bank, owned by a department.

    Departmental rather than personal on purpose: the commonest way an
    institution loses years of assessment material is a lecturer leaving with
    it on a laptop.
    """
    from acmis.modules.shared.models import AcademicUnit

    unit = get_or_404(ctx, AcademicUnit, payload.owning_unit_id) if payload.owning_unit_id else None
    departments = [str(unit.id)] if unit else [str(d) for d in ctx.principal.department_ids]
    authorize(
        engine=ctx.engine,
        action="question_bank:create",
        resource_type="question_bank",
        resource={
            "id": None,
            "course_id": str(payload.course_id) if payload.course_id else None,
            "department_ids": departments,
            "faculty_ids": [str(a) for a in (unit.ancestor_ids if unit else ())],
            "is_shared": payload.is_shared,
        },
        category=AuditCategory.ASSESSMENT,
    )
    bank = QuestionBank(
        **payload.model_dump(),
        department_ids=[unit.id] if unit else sorted(ctx.principal.department_ids),
        faculty_ids=list(unit.ancestor_ids or ()) if unit else sorted(ctx.principal.faculty_ids),
        created_by_id=ctx.principal.id,
    )
    ctx.db.add(bank)
    ctx.db.flush()
    return BankOut.model_validate(bank)


@router.post(
    "/banks/{bank_id}/questions",
    response_model=QuestionOut,
    status_code=status.HTTP_201_CREATED,
)
def add_question(bank_id: uuid.UUID, payload: QuestionIn, ctx: StaffContext) -> QuestionOut:
    bank = get_or_404(ctx, QuestionBank, bank_id)
    authorize(
        engine=ctx.engine,
        action="question:create",
        resource_type="question",
        resource={
            "id": None,
            "bank_id": str(bank.id),
            "kind": payload.kind,
            "is_locked": False,
            "is_active": True,
            "is_shared": bank.is_shared,
            "department_ids": [str(d) for d in bank.department_ids],
            "faculty_ids": [str(f) for f in bank.faculty_ids],
        },
        category=AuditCategory.ASSESSMENT,
    )
    question = service.create_question(
        ctx.db,
        bank=bank,
        payload={
            **payload.model_dump(exclude={"options"}),
            "options": [o.model_dump() for o in payload.options],
        },
        actor_id=ctx.principal.id,
    )
    return QuestionOut.model_validate(question)


@router.get("/banks/{bank_id}/questions", response_model=Page[QuestionOut])
def list_questions(
    bank_id: uuid.UUID,
    ctx: StaffContext,
    page: PageQuery,
    topic: str | None = None,
    kind: str | None = None,
    include_answers: bool = False,
) -> Page[QuestionOut]:
    """Browse a bank.

    `include_answers` is gated by a separate action, because reading the answer
    keys of a live paper is the one disclosure that invalidates a whole
    cohort's sitting — `learning.answer-key-confidentiality` refuses it while
    an assessment is open.
    """
    bank = get_or_404(ctx, QuestionBank, bank_id)
    decision = authorize(
        engine=ctx.engine,
        action="question:list",
        resource_type="question",
        resource={
            "id": None,
            "bank_id": str(bank.id),
            "is_shared": bank.is_shared,
            "is_active": True,
            "is_locked": False,
            "department_ids": [str(d) for d in bank.department_ids],
            "faculty_ids": [str(f) for f in bank.faculty_ids],
        },
        category=AuditCategory.ASSESSMENT,
    )
    if include_answers:
        authorize(
            engine=ctx.engine,
            action="question:read_answer_key",
            resource_type="question",
            resource={
                "id": None,
                "bank_id": str(bank.id),
                "department_ids": [str(d) for d in bank.department_ids],
                "assessment_status": "draft",
            },
            category=AuditCategory.ASSESSMENT,
            audit_reads=True,
        )

    stmt = select(Question).where(Question.bank_id == bank_id, Question.deleted_at.is_(None))
    if topic:
        stmt = stmt.where(Question.topic == topic)
    if kind:
        stmt = stmt.where(Question.kind == kind)
    found = keyset_page(
        ctx.db, stmt, page=page, key=Question.created_at, ident=Question.id, descending=True
    )

    items: list[QuestionOut] = []
    for row in found.rows:
        payload = QuestionOut.model_validate(row).model_dump()
        if not include_answers:
            payload.pop("answer_key", None)
            payload.pop("rubric", None)
        items.append(QuestionOut.model_construct(**decision.filter(payload)))
    return Page.of(items, limit=page.limit, next_cursor=found.next_cursor, total=found.total)


# ---------------------------------------------------------------------------
# Online assessments
# ---------------------------------------------------------------------------


class AssessmentIn(Schema):
    kind: Annotated[str, Field(pattern="^(practice|quiz|test|assignment|examination)$")]
    title: Annotated[str, Field(max_length=300)]
    instructions: str | None = None
    assessment_component_id: uuid.UUID | None = None
    pass_mark_percent: Annotated[int | None, Field(ge=0, le=100)] = None
    opens_at: datetime | None = None
    closes_at: datetime | None = None
    duration_minutes: Annotated[int | None, Field(ge=1, le=600)] = None
    max_attempts: Annotated[int, Field(ge=1, le=20)] = 1
    attempt_grading: Annotated[str, Field(pattern="^(best|latest|average|first)$")] = "best"
    behaviour: Annotated[
        str,
        Field(
            pattern="^(deferred_feedback|immediate_feedback|interactive_with_tries"
            "|adaptive|manual)$"
        ),
    ] = "deferred_feedback"
    tries_per_question: Annotated[int, Field(ge=1, le=10)] = 1
    try_penalty_fraction: Annotated[float, Field(ge=0, le=1)] = 0
    shuffle_questions: bool = True
    shuffle_options: bool = True
    one_question_per_page: bool = False
    allow_backtracking: bool = True
    allowed_ip_ranges: list[str] = Field(default_factory=list)
    monitor_focus_loss: bool = False
    require_webcam: bool = False
    score_visibility: Annotated[
        str, Field(pattern="^(never|immediately|after_close|on_release)$")
    ] = "on_release"
    show_correct_answers: bool = False
    show_explanations: bool = False


class AssessmentOut(Schema):
    id: uuid.UUID
    space_id: uuid.UUID
    course_offering_id: uuid.UUID
    kind: str
    title: str
    instructions: str | None
    assessment_component_id: uuid.UUID | None
    total_marks: float
    pass_mark_percent: int | None
    opens_at: datetime | None
    closes_at: datetime | None
    duration_minutes: int | None
    max_attempts: int
    attempt_grading: str
    behaviour: str
    tries_per_question: int
    shuffle_questions: bool
    score_visibility: str
    status: str
    authored_by_id: uuid.UUID | None
    reviewed_by_id: uuid.UUID | None
    reviewed_at: datetime | None
    review_comments: str | None
    released_at: datetime | None
    pushed_to_mark_sheet_at: datetime | None
    attempt_count: int
    submitted_count: int
    mean_score: float | None
    median_score: float | None
    standard_deviation: float | None
    pending_manual_marking: int


@router.post(
    "/spaces/{space_id}/assessments",
    response_model=AssessmentOut,
    status_code=status.HTTP_201_CREATED,
)
def create_assessment(
    space_id: uuid.UUID, payload: AssessmentIn, ctx: StaffContext
) -> AssessmentOut:
    space = get_or_404(ctx, CourseSpace, space_id)
    authorize(
        engine=ctx.engine,
        action="online_assessment:create",
        resource_type="online_assessment",
        resource={
            "id": None,
            "space_id": str(space.id),
            "course_offering_id": str(space.course_offering_id),
            "kind": payload.kind,
            "status": "draft",
            "department_ids": [str(d) for d in space.department_ids],
            "faculty_ids": [str(f) for f in space.faculty_ids],
        },
        category=AuditCategory.ASSESSMENT,
    )
    return AssessmentOut.model_validate(
        service.build_assessment(
            ctx.db, space=space, payload=payload.model_dump(), actor_id=ctx.principal.id
        )
    )


@router.get("/assessments/{assessment_id}", response_model=RecordEnvelope[AssessmentOut])
def get_assessment(assessment_id: uuid.UUID, ctx: AnyContext) -> RecordEnvelope[AssessmentOut]:
    """One assessment, with what the caller may do to it.

    Capabilities come back with the record so the UI renders only the buttons
    that will work. A student reaching this sees the assessment they are
    sitting; the policy decides which, and `is_registered`/`is_open` are
    supplied here because neither is a column on the row.
    """
    assessment = get_or_404(ctx, OnlineAssessment, assessment_id)
    is_student = ctx.principal.kind == "student"
    decision = authorize(
        engine=ctx.engine,
        action="online_assessment:read",
        resource_type="online_assessment",
        resource=assessment,
        extra_attributes={
            "is_registered": (
                service_is_registered(ctx, assessment.course_offering_id) if is_student else True
            ),
        },
        category=AuditCategory.ASSESSMENT,
    )
    payload = AssessmentOut.model_validate(assessment).model_dump()
    return RecordEnvelope(
        data=AssessmentOut.model_construct(**decision.filter(payload)),
        capabilities=service.capabilities_for(ctx, assessment),
        masked_fields=sorted(decision.masked_fields),
    )


@router.get("/spaces/{space_id}/assessments", response_model=list[AssessmentOut])
def list_space_assessments(space_id: uuid.UUID, ctx: AnyContext) -> list[AssessmentOut]:
    """Assessments in a course space.

    A student sees only what is open or released to them; staff see everything
    including drafts. Filtered in the query as well as decided by policy, so a
    draft paper never leaves the database for a candidate.
    """
    space = get_or_404(ctx, CourseSpace, space_id)
    is_student = ctx.principal.kind == "student"
    authorize(
        engine=ctx.engine,
        action="online_assessment:list",
        resource_type="online_assessment",
        resource={
            "id": None,
            "space_id": str(space.id),
            "course_offering_id": str(space.course_offering_id),
            "status": "open",
            "department_ids": [str(d) for d in space.department_ids],
            "faculty_ids": [str(f) for f in space.faculty_ids],
        },
        extra_attributes={
            "is_registered": (
                service_is_registered(ctx, space.course_offering_id) if is_student else True
            )
        },
        category=AuditCategory.ASSESSMENT,
    )
    stmt = select(OnlineAssessment).where(
        OnlineAssessment.space_id == space_id,
        OnlineAssessment.deleted_at.is_(None),
    )
    if is_student:
        stmt = stmt.where(OnlineAssessment.status.in_(["open", "closed", "marked", "released"]))
    rows = (
        ctx.db.execute(stmt.order_by(OnlineAssessment.opens_at.desc().nullslast())).scalars().all()
    )
    return [AssessmentOut.model_validate(r) for r in rows]


@router.get("/me/attempts", response_model=list[dict[str, Any]])
def my_attempts(ctx: StudentContext) -> list[dict[str, Any]]:
    """A student's own attempts, with whether each score is visible yet.

    `score_visible` is computed here rather than left to the UI: it depends on
    the assessment's `score_visibility` setting and its release state, and a
    client that got it wrong would show a provisional mark as final.
    """
    from acmis.modules.learning.models import Attempt

    rows = (
        ctx.db.execute(
            select(Attempt)
            .where(
                Attempt.student_id == ctx.student_id,
                Attempt.deleted_at.is_(None),
            )
            .order_by(Attempt.started_at.desc())
        )
        .scalars()
        .all()
    )

    out: list[dict[str, Any]] = []
    for attempt in rows:
        assessment = ctx.db.get(OnlineAssessment, attempt.assessment_id)
        if assessment is None:
            continue
        visible = _score_visible(assessment, attempt)
        authorize(
            engine=ctx.engine,
            action="assessment_attempt:read",
            resource_type="assessment_attempt",
            resource=attempt,
            extra_attributes={"score_visible": visible},
            category=AuditCategory.ASSESSMENT,
        )
        out.append(
            {
                "id": str(attempt.id),
                "assessment_id": str(assessment.id),
                "assessment_title": assessment.title,
                "assessment_kind": assessment.kind,
                "attempt_number": attempt.attempt_number,
                "status": attempt.status,
                "started_at": attempt.started_at.isoformat(),
                "submitted_at": (
                    attempt.submitted_at.isoformat() if attempt.submitted_at else None
                ),
                "expires_at": attempt.expires_at.isoformat() if attempt.expires_at else None,
                "total_marks": float(assessment.total_marks),
                # Withheld rather than nulled when not yet visible, and the
                # flag says which — a null score and a sealed score are
                # different facts.
                "score_visible": visible,
                "total_score": float(attempt.total_score)
                if visible and attempt.total_score is not None
                else None,
                "percentage": float(attempt.percentage)
                if visible and attempt.percentage is not None
                else None,
            }
        )
    return out


def _score_visible(assessment: OnlineAssessment, attempt: Any) -> bool:
    """Whether this candidate may see this score yet.

    Four settings, and the default (`on_release`) is the only safe one for
    anything that counts: candidates compare notes within minutes, so a score
    shown before marking is complete produces an argument the institution
    cannot win.
    """
    from acmis.modules.learning.models import AssessmentStatus, AttemptStatus

    if attempt.status not in {AttemptStatus.MARKED, AttemptStatus.SUBMITTED, AttemptStatus.EXPIRED}:
        return False
    setting = assessment.score_visibility
    if setting == "never":
        return False
    if setting == "immediately":
        return bool(attempt.status == AttemptStatus.MARKED)
    if setting == "after_close":
        return assessment.status in {
            AssessmentStatus.CLOSED,
            AssessmentStatus.MARKED,
            AssessmentStatus.RELEASED,
        }
    return bool(assessment.status == AssessmentStatus.RELEASED)


def _candidate_view(attempt: Any, assessment: OnlineAssessment) -> AttemptOut:
    """An attempt as its own candidate may see it.

    The auto-marked total exists the moment a paper is submitted, and on a
    `on_release` paper the candidate must not have it: with pooled draws they
    would compare scores, work out who got the easy pool, and be right. So the
    marks are stripped from the response the candidate's own browser gets,
    rather than relying on the client not to render them.
    """
    view = AttemptOut.model_validate(attempt)
    if not _score_visible(assessment, attempt):
        view = view.model_copy(update={"total_score": None, "percentage": None, "marked_at": None})
    return view


class ItemIn(Schema):
    sequence: int = 0
    section: str | None = None
    mode: Annotated[str, Field(pattern="^(fixed|pooled)$")] = "fixed"
    question_id: uuid.UUID | None = None
    bank_id: uuid.UUID | None = None
    draw_count: Annotated[int, Field(ge=1, le=50)] = 1
    draw_filters: dict[str, Any] = Field(default_factory=dict)
    marks_override: float | None = None
    is_mandatory: bool = True


@router.post("/assessments/{assessment_id}/items", response_model=dict)
def add_item(assessment_id: uuid.UUID, payload: ItemIn, ctx: StaffContext) -> dict[str, Any]:
    """Add a question, or a random draw from a bank.

    A pooled item is what makes online testing at scale viable: every
    candidate gets a different but equivalent paper, so a leaked question set
    is worth much less. The drawn set is recorded per attempt, which is what
    keeps a candidate's paper reproducible when they query their mark.
    """
    from acmis.modules.learning.models import AssessmentItem

    assessment = get_or_404(ctx, OnlineAssessment, assessment_id)
    authorize(
        engine=ctx.engine,
        action="online_assessment:update",
        resource_type="online_assessment",
        resource=assessment,
        category=AuditCategory.ASSESSMENT,
    )
    if assessment.status not in {"draft", "review"}:
        raise Conflict(f"A {assessment.status} assessment cannot be changed.")

    item = AssessmentItem(
        assessment_id=assessment.id, **payload.model_dump(), created_by_id=ctx.principal.id
    )
    ctx.db.add(item)
    ctx.db.flush()
    ctx.db.refresh(assessment)
    total = service.recompute_total_marks(ctx.db, assessment=assessment)
    return {"id": str(item.id), "total_marks": total}


@router.post("/assessments/{assessment_id}/submit-for-review", response_model=AssessmentOut)
def submit_for_review(assessment_id: uuid.UUID, ctx: StaffContext) -> AssessmentOut:
    assessment = get_or_404(ctx, OnlineAssessment, assessment_id)
    authorize(
        engine=ctx.engine,
        action="online_assessment:submit_for_review",
        resource_type="online_assessment",
        resource=assessment,
        category=AuditCategory.ASSESSMENT,
    )
    return AssessmentOut.model_validate(
        service.submit_for_review(ctx.db, assessment=assessment, actor_id=ctx.principal.id)
    )


class ReviewIn(Schema):
    approve: bool
    comments: str | None = None


@router.post("/assessments/{assessment_id}/review", response_model=AssessmentOut)
def review(assessment_id: uuid.UUID, payload: ReviewIn, ctx: StaffContext) -> AssessmentOut:
    assessment = get_or_404(ctx, OnlineAssessment, assessment_id)
    authorize(
        engine=ctx.engine,
        action="online_assessment:review",
        resource_type="online_assessment",
        resource=assessment,
        category=AuditCategory.ASSESSMENT,
    )
    return AssessmentOut.model_validate(
        service.review_assessment(
            ctx.db,
            assessment=assessment,
            approve=payload.approve,
            comments=payload.comments,
            actor_id=ctx.principal.id,
        )
    )


@router.post("/assessments/{assessment_id}/open", response_model=AssessmentOut)
def open_assessment(assessment_id: uuid.UUID, ctx: StaffContext) -> AssessmentOut:
    from acmis.core.audit import emit
    from acmis.modules.learning.models import AssessmentStatus

    assessment = get_or_404(ctx, OnlineAssessment, assessment_id)
    authorize(
        engine=ctx.engine,
        action="online_assessment:open",
        resource_type="online_assessment",
        resource=assessment,
        category=AuditCategory.ASSESSMENT,
    )
    if assessment.status != AssessmentStatus.SCHEDULED:
        raise Conflict("Only a reviewed and scheduled assessment can be opened.")
    assessment.status = AssessmentStatus.OPEN
    ctx.db.flush()
    emit(
        "online_assessment:open",
        AuditCategory.ASSESSMENT,
        resource_type="online_assessment",
        resource_id=assessment.id,
        resource_label=assessment.title,
        summary="Opened to candidates",
        severity="notice",
    )
    return AssessmentOut.model_validate(assessment)


# ---------------------------------------------------------------------------
# Sitting
# ---------------------------------------------------------------------------


class StartAttemptIn(Schema):
    password: str | None = None


class PresentedQuestionOut(Schema):
    question_id: uuid.UUID
    sequence: int
    kind: str
    stem: str
    marks: float
    section: str | None
    #: Options in this candidate's order, with `is_correct` stripped.
    options: list[dict[str, Any]] = Field(default_factory=list)
    #: The variable set for a calculated question, so the stem can be
    #: rendered with this candidate's numbers.
    variables: dict[str, Any] = Field(default_factory=dict)
    answer: dict[str, Any] = Field(default_factory=dict)
    flagged: bool = False


class AttemptOut(Schema):
    id: uuid.UUID
    assessment_id: uuid.UUID
    attempt_number: int
    status: str
    started_at: datetime
    expires_at: datetime | None
    submitted_at: datetime | None
    extra_time_minutes: int
    total_score: float | None
    percentage: float | None
    marked_at: datetime | None


@router.post(
    "/assessments/{assessment_id}/attempts",
    response_model=AttemptOut,
    status_code=status.HTTP_201_CREATED,
)
def start_attempt(
    assessment_id: uuid.UUID,
    request: Request,
    ctx: StudentContext,
    payload: StartAttemptIn | None = None,
) -> AttemptOut:
    """Begin (or resume) a sitting.

    Resuming rather than restarting after a dropped connection is deliberate:
    the frozen paper is returned unchanged, because a reshuffle on resume looks
    to a candidate exactly like the system losing their answers.
    """
    body = payload or StartAttemptIn()
    assessment = get_or_404(ctx, OnlineAssessment, assessment_id)
    authorize(
        engine=ctx.engine,
        action="online_assessment:start",
        resource_type="online_assessment",
        resource={
            **{
                "id": str(assessment.id),
                "course_offering_id": str(assessment.course_offering_id),
                "kind": assessment.kind,
                "status": assessment.status,
                "is_open": assessment.is_open_now(),
            },
            "is_registered": service_is_registered(ctx, assessment.course_offering_id),
        },
        category=AuditCategory.ASSESSMENT,
    )
    return _candidate_view(
        service.start_attempt(
            ctx.db,
            assessment=assessment,
            student_id=ctx.student_id,
            password=body.password,
            ip_address=ctx.context.ip_address,
            user_agent=ctx.context.user_agent,
        ),
        assessment,
    )


@router.get("/attempts/{attempt_id}/paper", response_model=list[PresentedQuestionOut])
def get_paper(attempt_id: uuid.UUID, ctx: StudentContext) -> list[PresentedQuestionOut]:
    """The candidate's paper, as they saw it, without any answer keys.

    Options are stripped of `is_correct` and the explanation is withheld —
    belt and braces on top of `learning.answer-key-confidentiality`, because
    this is the endpoint a candidate's own browser calls and the one place a
    leak would be most convenient.
    """
    attempt = get_or_404(ctx, Attempt, attempt_id)
    authorize(
        engine=ctx.engine,
        action="assessment_attempt:read",
        resource_type="assessment_attempt",
        resource=attempt,
        category=AuditCategory.ASSESSMENT,
    )

    responses = (
        ctx.db.execute(
            select(AttemptResponse)
            .where(AttemptResponse.attempt_id == attempt.id)
            .order_by(AttemptResponse.sequence)
        )
        .scalars()
        .all()
    )

    order_by_question = {
        entry["question_id"]: entry
        for entry in (attempt.presented_paper or {}).get("questions", [])
    }

    out: list[PresentedQuestionOut] = []
    for response in responses:
        question = ctx.db.get(Question, response.question_id)
        if question is None:
            continue
        entry = order_by_question.get(str(question.id), {})
        option_order = entry.get("option_order") or [o.label for o in question.options]
        by_label = {o.label: o for o in question.options}
        out.append(
            PresentedQuestionOut(
                question_id=question.id,
                sequence=response.sequence,
                kind=question.kind,
                stem=_render_stem(question.stem, response.variables),
                marks=float(response.marks_available),
                section=entry.get("section"),
                options=[
                    {"label": label, "body": by_label[label].body}
                    for label in option_order
                    if label in by_label
                ],
                variables=response.variables or {},
                answer=response.answer or {},
                flagged=response.flagged,
            )
        )
    return out


def _render_stem(stem: str, variables: dict[str, Any] | None) -> str:
    """Substitute a calculated question's variables into its stem.

    `{a}` and `{b}` placeholders, Moodle's convention. Done here rather than in
    the browser so a candidate cannot see the unsubstituted template — which
    would tell them the question is parameterised and that their neighbour has
    different numbers.
    """
    if not variables:
        return stem
    rendered = stem
    for key, value in variables.items():
        rendered = rendered.replace(f"{{{key}}}", str(value))
    return rendered


class SaveAnswerIn(Schema):
    question_id: uuid.UUID
    answer: dict[str, Any] = Field(default_factory=dict)
    seconds_spent: Annotated[int, Field(ge=0, le=86400)] = 0
    flagged: bool = False


@router.put("/attempts/{attempt_id}/answers", status_code=status.HTTP_204_NO_CONTENT)
def save_answer(attempt_id: uuid.UUID, payload: SaveAnswerIn, ctx: StudentContext) -> None:
    """Save one answer as it is given.

    Called on every change, not at submission. A power cut in the third hour of
    an examination must not cost a candidate their paper.
    """
    attempt = get_or_404(ctx, Attempt, attempt_id)
    authorize(
        engine=ctx.engine,
        action="assessment_attempt:save",
        resource_type="assessment_attempt",
        resource=attempt,
        category=AuditCategory.ASSESSMENT,
    )
    service.save_response(
        ctx.db,
        attempt=attempt,
        question_id=payload.question_id,
        answer=payload.answer,
        seconds_spent=payload.seconds_spent,
        flagged=payload.flagged,
    )


class IntegrityEventIn(Schema):
    kind: Annotated[str, Field(pattern="^(focus_loss|paste|resize|offline|reconnect)$")]
    detail: dict[str, Any] = Field(default_factory=dict)


@router.post("/attempts/{attempt_id}/integrity", status_code=status.HTTP_204_NO_CONTENT)
def report_integrity_event(
    attempt_id: uuid.UUID, payload: IntegrityEventIn, ctx: StudentContext
) -> None:
    """Record a client-reported integrity signal.

    A signal, never a verdict. A focus loss in Gulu and a candidate opening
    another tab are indistinguishable from here; an invigilator reads these
    and weighs them, and nothing in the system acts on them by itself.
    """
    attempt = get_or_404(ctx, Attempt, attempt_id)
    if attempt.student_id != ctx.student_id:
        raise NotFound()
    service.record_integrity_event(
        ctx.db, attempt=attempt, kind=payload.kind, detail=payload.detail
    )


@router.post("/attempts/{attempt_id}/submit", response_model=AttemptOut)
def submit_attempt(attempt_id: uuid.UUID, ctx: StudentContext) -> AttemptOut:
    attempt = get_or_404(ctx, Attempt, attempt_id)
    authorize(
        engine=ctx.engine,
        action="assessment_attempt:submit",
        resource_type="assessment_attempt",
        resource=attempt,
        category=AuditCategory.ASSESSMENT,
    )
    submitted = service.submit_attempt(ctx.db, attempt=attempt, actor_id=ctx.principal.id)
    return _candidate_view(submitted, submitted.assessment)


# ---------------------------------------------------------------------------
# Marking
# ---------------------------------------------------------------------------


class MarkingQueueRow(Schema):
    response_id: uuid.UUID
    attempt_id: uuid.UUID
    question_id: uuid.UUID
    question_kind: str
    question_stem: str
    marks_available: float
    answer: dict[str, Any]
    rubric: list[dict[str, Any]]
    #: Absent when the assignment or assessment is blind-marked. Honoured by
    #: not sending the identity, not by asking markers not to look.
    student_reference: str | None = None


@router.get("/assessments/{assessment_id}/marking-queue", response_model=list[MarkingQueueRow])
def marking_queue(assessment_id: uuid.UUID, ctx: StaffContext) -> list[MarkingQueueRow]:
    assessment = get_or_404(ctx, OnlineAssessment, assessment_id)
    decision = authorize(
        engine=ctx.engine,
        action="assessment_attempt:mark",
        resource_type="assessment_attempt",
        resource={
            "id": None,
            "assessment_id": str(assessment.id),
            "course_offering_id": str(assessment.course_offering_id),
            "status": "submitted",
            "department_ids": [str(d) for d in assessment.department_ids],
            "faculty_ids": [str(f) for f in assessment.faculty_ids],
        },
        category=AuditCategory.ASSESSMENT,
    )

    rows = (
        ctx.db.execute(
            select(AttemptResponse)
            .join(Attempt, AttemptResponse.attempt_id == Attempt.id)
            .where(
                Attempt.assessment_id == assessment.id,
                AttemptResponse.marks_awarded.is_(None),
            )
            .order_by(AttemptResponse.question_id, AttemptResponse.sequence)
        )
        .scalars()
        .all()
    )

    blind = "student_id" in decision.masked_fields
    out: list[MarkingQueueRow] = []
    for response in rows:
        question = ctx.db.get(Question, response.question_id)
        if question is None:
            continue
        out.append(
            MarkingQueueRow(
                response_id=response.id,
                attempt_id=response.attempt_id,
                question_id=question.id,
                question_kind=question.kind,
                question_stem=question.stem,
                marks_available=float(response.marks_available),
                answer=response.answer or {},
                rubric=question.rubric or [],
                # Grouped by question rather than by candidate, and identity
                # withheld when the decision masks it: marking every script's
                # question 3 together is both faster and more consistent than
                # marking script by script.
                student_reference=None if blind else str(response.attempt_id)[-6:],
            )
        )
    return out


class ManualMarkIn(Schema):
    marks: Annotated[float, Field(ge=0)]
    comment: str | None = None
    rubric_scores: list[dict[str, Any]] = Field(default_factory=list)


@router.post("/responses/{response_id}/mark", response_model=dict)
def mark_manually(
    response_id: uuid.UUID, payload: ManualMarkIn, ctx: StaffContext
) -> dict[str, Any]:
    response = get_or_404(ctx, AttemptResponse, response_id)
    authorize(
        engine=ctx.engine,
        action="assessment_response:mark",
        resource_type="assessment_response",
        resource=response,
        category=AuditCategory.ASSESSMENT,
    )
    marked = service.mark_response_manually(
        ctx.db,
        response=response,
        marks=payload.marks,
        comment=payload.comment,
        rubric_scores=payload.rubric_scores,
        actor_id=ctx.principal.id,
    )
    return {
        "response_id": str(marked.id),
        "marks_awarded": float(marked.marks_awarded or 0),
    }


@router.post("/assessments/{assessment_id}/release", response_model=AssessmentOut)
def release(assessment_id: uuid.UUID, ctx: StaffContext) -> AssessmentOut:
    assessment = get_or_404(ctx, OnlineAssessment, assessment_id)
    authorize(
        engine=ctx.engine,
        action="online_assessment:release",
        resource_type="online_assessment",
        resource=assessment,
        category=AuditCategory.ASSESSMENT,
    )
    return AssessmentOut.model_validate(
        service.release_assessment(ctx.db, assessment=assessment, actor_id=ctx.principal.id)
    )


@router.post("/assessments/{assessment_id}/push-marks", response_model=dict)
def push_marks(assessment_id: uuid.UUID, ctx: StaffContext) -> dict[str, Any]:
    """Write released scores into the course's mark sheet.

    A component score on a draft mark sheet, and nothing else. The approval
    chain — moderation, department board, faculty board, Senate — still governs
    every mark that reaches a transcript. Pushing also makes the pusher an
    entrant on the sheet, so they can no longer approve it: pushing marks is
    entering marks.
    """
    from acmis.modules.assessment.models import MarkSheet

    assessment = get_or_404(ctx, OnlineAssessment, assessment_id)
    sheet = ctx.db.execute(
        select(MarkSheet).where(MarkSheet.course_offering_id == assessment.course_offering_id)
    ).scalar_one_or_none()

    authorize(
        engine=ctx.engine,
        action="online_assessment:push_marks",
        resource_type="online_assessment",
        resource=assessment,
        extra_attributes={"mark_sheet_status": sheet.status if sheet else None},
        category=AuditCategory.ASSESSMENT,
    )
    return service.push_to_mark_sheet(ctx.db, assessment=assessment, actor_id=ctx.principal.id)


# ---------------------------------------------------------------------------
# Assignments
# ---------------------------------------------------------------------------


class AssignmentOut(Schema):
    id: uuid.UUID
    space_id: uuid.UUID
    course_offering_id: uuid.UUID
    title: str
    brief: str
    total_marks: float
    due_at: datetime
    accept_until: datetime | None
    late_penalty_percent_per_day: float
    submission_mode: str
    blind_marking: bool
    double_marking: bool
    status: str


class SubmissionOut(Schema):
    id: uuid.UUID
    assignment_id: uuid.UUID
    student_id: uuid.UUID
    attempt_number: int
    submitted_at: datetime | None
    days_late: int
    penalty_percent: float
    status: str
    raw_score: float | None
    final_score: float | None
    percentage: float | None
    feedback: str | None
    similarity_percent: float | None


class SubmitAssignmentIn(Schema):
    attachment_ids: list[uuid.UUID] = Field(default_factory=list)
    text_response: str | None = None


@router.post(
    "/assignments/{assignment_id}/submissions",
    response_model=SubmissionOut,
    status_code=status.HTTP_201_CREATED,
)
def submit_assignment(
    assignment_id: uuid.UUID, payload: SubmitAssignmentIn, ctx: StudentContext
) -> SubmissionOut:
    assignment = get_or_404(ctx, Assignment, assignment_id)
    authorize(
        engine=ctx.engine,
        action="assignment_submission:create",
        resource_type="assignment_submission",
        resource={
            "id": None,
            "assignment_id": str(assignment.id),
            "student_id": str(ctx.student_id),
            "course_offering_id": str(assignment.course_offering_id),
            "status": "draft",
        },
        extra_attributes={
            "is_registered": service_is_registered(ctx, assignment.course_offering_id)
        },
        category=AuditCategory.ASSESSMENT,
    )
    return SubmissionOut.model_validate(
        service.submit_assignment(
            ctx.db,
            assignment=assignment,
            student_id=ctx.student_id,
            attachment_ids=payload.attachment_ids,
            text_response=payload.text_response,
            actor_id=ctx.principal.id,
        )
    )


class MarkSubmissionIn(Schema):
    raw_score: Annotated[float, Field(ge=0)]
    rubric_scores: list[dict[str, Any]] = Field(default_factory=list)
    feedback: str | None = None
    is_second_marker: bool = False


@router.post("/submissions/{submission_id}/mark", response_model=SubmissionOut)
def mark_submission(
    submission_id: uuid.UUID, payload: MarkSubmissionIn, ctx: StaffContext
) -> SubmissionOut:
    submission = get_or_404(ctx, Submission, submission_id)
    authorize(
        engine=ctx.engine,
        action=(
            "assignment_submission:second_mark"
            if payload.is_second_marker
            else "assignment_submission:mark"
        ),
        resource_type="assignment_submission",
        resource=submission,
        category=AuditCategory.ASSESSMENT,
    )
    return SubmissionOut.model_validate(
        service.mark_submission(
            ctx.db,
            submission=submission,
            raw_score=payload.raw_score,
            rubric_scores=payload.rubric_scores,
            feedback=payload.feedback,
            actor_id=ctx.principal.id,
            is_second_marker=payload.is_second_marker,
        )
    )


# ---------------------------------------------------------------------------
# Engagement
# ---------------------------------------------------------------------------


class EngagementOut(Schema):
    student_id: uuid.UUID
    week_number: int
    materials_available: int
    materials_viewed: int
    minutes_on_material: int
    assessments_available: int
    assessments_attempted: int
    mean_assessment_percent: float | None
    days_since_last_activity: int | None
    risk_band: str | None


@router.get("/offerings/{offering_id}/engagement", response_model=list[EngagementOut])
def engagement(
    offering_id: uuid.UUID, ctx: StaffContext, week_number: int | None = None
) -> list[EngagementOut]:
    """Engagement for a course, for the early-warning conversation.

    A prompt to look, not a decision. Nothing in the system reads `risk_band`
    to act — a heuristic like this will always misjudge the student with one
    shared laptop and no data bundle, and the person looking is the one who
    decides.
    """
    from acmis.modules.learning.models import EngagementSnapshot

    authorize(
        engine=ctx.engine,
        action="engagement_snapshot:list",
        resource_type="engagement_snapshot",
        resource={
            "id": None,
            "course_offering_id": str(offering_id),
            "risk_band": None,
            "week_number": week_number,
        },
        category=AuditCategory.CURRICULUM,
    )
    stmt = select(EngagementSnapshot).where(EngagementSnapshot.course_offering_id == offering_id)
    if week_number:
        stmt = stmt.where(EngagementSnapshot.week_number == week_number)
    rows = (
        ctx.db.execute(
            stmt.order_by(EngagementSnapshot.week_number.desc(), EngagementSnapshot.risk_band)
        )
        .scalars()
        .all()
    )
    return [EngagementOut.model_validate(r) for r in rows]


@router.post("/offerings/{offering_id}/engagement/capture", response_model=dict)
def capture_engagement(
    offering_id: uuid.UUID, week_number: int, ctx: StaffContext
) -> dict[str, Any]:
    authorize(
        engine=ctx.engine,
        action="engagement_snapshot:capture",
        resource_type="engagement_snapshot",
        resource={"id": None, "course_offering_id": str(offering_id), "risk_band": None},
        category=AuditCategory.CURRICULUM,
    )
    return service.capture_engagement(
        ctx.db, course_offering_id=offering_id, week_number=week_number
    )
