"""Assessment, grading, boards and awards endpoints."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query, status
from pydantic import Field
from sqlalchemy import select

from acmis.core.abac import authorize
from acmis.core.audit import AuditCategory
from acmis.core.deps import AnyContext, PageQuery, StaffContext, StudentContext
from acmis.core.pagination import keyset_page
from acmis.core.schemas import BulkResult, Page, Reason, RecordEnvelope, Schema
from acmis.modules.assessment import service
from acmis.modules.assessment.models import (
    Award,
    CourseResult,
    GraduationList,
    MarkSheet,
)
from acmis.routers._common import get_or_404

router = APIRouter(prefix="/assessment", tags=["assessment"])


class MarkSheetOut(Schema):
    id: uuid.UUID
    course_offering_id: uuid.UUID
    semester_id: uuid.UUID
    status: str
    student_count: int
    entered_count: int
    missing_count: int
    pass_count: int
    fail_count: int
    mean_mark: float | None
    median_mark: float | None
    standard_deviation: float | None
    grade_distribution: dict[str, Any]
    submitted_at: datetime | None
    moderated_at: datetime | None
    moderation_adjustment: float | None
    board_approved_at: datetime | None
    faculty_approved_at: datetime | None
    senate_approved_at: datetime | None
    published_at: datetime | None
    due_on: date | None
    return_comments: str | None


class ResultRowOut(Schema):
    id: uuid.UUID
    student_id: uuid.UUID
    course_code: str
    course_title: str
    credit_units: int
    coursework_mark: float | None
    exam_mark: float | None
    final_mark: float | None
    grade: str | None
    grade_point: float | None
    outcome: str
    attempt_number: int
    is_retake: bool
    is_superseded: bool
    released: bool
    withheld: bool


@router.get("/mark-sheets", response_model=Page[MarkSheetOut])
def list_mark_sheets(
    ctx: StaffContext,
    page: PageQuery,
    semester_id: uuid.UUID | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    mine_only: bool = False,
) -> Page[MarkSheetOut]:
    """List mark sheets in the caller's reach.

    `mine_only` filters to the offerings the caller is actually allocated to
    teach, which is the default view for a lecturer — a department's full list
    is noise to someone with three courses.
    """
    authorize(
        engine=ctx.engine,
        action="mark_sheet:list",
        resource_type="mark_sheet",
        resource={"id": None, "status": status_filter},
        category=AuditCategory.ASSESSMENT,
    )
    stmt = select(MarkSheet).where(MarkSheet.deleted_at.is_(None))
    if semester_id:
        stmt = stmt.where(MarkSheet.semester_id == semester_id)
    if status_filter:
        stmt = stmt.where(MarkSheet.status == status_filter)

    if mine_only:
        assigned = [
            uuid.UUID(i) for i in ctx.principal.extra.get("assigned_course_offering_ids", [])
        ]
        stmt = stmt.where(MarkSheet.course_offering_id.in_(assigned or [uuid.UUID(int=0)]))
    else:
        reach = ctx.principal.department_ids | ctx.principal.faculty_ids
        if reach and "results:senate_approve" not in ctx.principal.permissions:
            stmt = stmt.where(
                MarkSheet.department_ids.overlap(sorted(reach))
                | MarkSheet.faculty_ids.overlap(sorted(reach))
            )

    found = keyset_page(
        ctx.db, stmt, page=page, key=MarkSheet.due_on, ident=MarkSheet.id, nulls="last"
    )
    return Page.of(
        [MarkSheetOut.model_validate(r) for r in found.rows],
        limit=page.limit,
        next_cursor=found.next_cursor,
        total=found.total,
    )


@router.post("/mark-sheets", response_model=MarkSheetOut, status_code=status.HTTP_201_CREATED)
def generate_mark_sheet(course_offering_id: uuid.UUID, ctx: StaffContext) -> MarkSheetOut:
    from acmis.modules.curriculum.models import CourseOffering

    offering = get_or_404(ctx, CourseOffering, course_offering_id)
    authorize(
        engine=ctx.engine,
        action="mark_sheet:create",
        resource_type="course_offering",
        resource=offering,
        category=AuditCategory.ASSESSMENT,
    )
    return MarkSheetOut.model_validate(
        service.generate_mark_sheet(
            ctx.db, course_offering_id=course_offering_id, actor_id=ctx.principal.id
        )
    )


@router.get("/mark-sheets/{sheet_id}", response_model=RecordEnvelope[MarkSheetOut])
def get_mark_sheet(sheet_id: uuid.UUID, ctx: StaffContext) -> RecordEnvelope[MarkSheetOut]:
    sheet = get_or_404(ctx, MarkSheet, sheet_id)
    authorize(
        engine=ctx.engine,
        action="mark_sheet:read",
        resource_type="mark_sheet",
        resource=sheet,
        category=AuditCategory.ASSESSMENT,
    )
    return RecordEnvelope(
        data=MarkSheetOut.model_validate(sheet),
        capabilities=service.capabilities_for(ctx, sheet),
    )


@router.get("/mark-sheets/{sheet_id}/results", response_model=list[ResultRowOut])
def get_mark_sheet_results(sheet_id: uuid.UUID, ctx: StaffContext) -> list[ResultRowOut]:
    sheet = get_or_404(ctx, MarkSheet, sheet_id)
    authorize(
        engine=ctx.engine,
        action="mark_sheet:read",
        resource_type="mark_sheet",
        resource=sheet,
        category=AuditCategory.ASSESSMENT,
        audit_reads=True,
    )
    rows = (
        ctx.db.execute(
            select(CourseResult)
            .where(CourseResult.mark_sheet_id == sheet.id, CourseResult.deleted_at.is_(None))
            .order_by(CourseResult.student_id)
        )
        .scalars()
        .all()
    )
    return [ResultRowOut.model_validate(r) for r in rows]


class MarkEntryIn(Schema):
    student_id: uuid.UUID
    #: {"CW1": 18, "TEST": 12, "EXAM": 58} — keyed by component code, so an
    #: uploaded spreadsheet maps to the assessment scheme rather than to
    #: positional columns that shift between courses.
    components: dict[str, float | None] = Field(default_factory=dict)
    #: `absent`, `malpractice`, `deferred`, `withheld`. A blank score and an
    #: absence are different facts with different consequences.
    exception: str | None = None


class MarkEntryBatchIn(Schema):
    entries: Annotated[list[MarkEntryIn], Field(min_length=1, max_length=2000)]


@router.post("/mark-sheets/{sheet_id}/marks", response_model=BulkResult)
def enter_marks(sheet_id: uuid.UUID, payload: MarkEntryBatchIn, ctx: StaffContext) -> BulkResult:
    """Enter or amend marks on a sheet.

    Partial success. 480 rows landing and six failing on an unrecognised
    student number is the normal outcome of an upload, and reporting it as one
    boolean forces a re-upload of all 486 — which is how marks get entered
    twice.
    """
    sheet = get_or_404(ctx, MarkSheet, sheet_id)
    authorize(
        engine=ctx.engine,
        action="mark_sheet:update",
        resource_type="mark_sheet",
        resource=sheet,
        category=AuditCategory.ASSESSMENT,
    )
    return service.enter_marks(
        ctx.db,
        sheet=sheet,
        entries=[e.model_dump() for e in payload.entries],
        actor_id=ctx.principal.id,
    )


class SheetTransitionIn(Schema):
    note: str | None = None
    minute_reference: str | None = None
    #: A cohort-wide scaling. Requires a note — a silent scaling is
    #: indistinguishable from tampering.
    adjustment: float | None = None


@router.post("/mark-sheets/{sheet_id}/{action}", response_model=MarkSheetOut)
def transition_mark_sheet(
    sheet_id: uuid.UUID,
    action: str,
    ctx: StaffContext,
    # Optional, because every field on it is. A submit or an approve carries no
    # note in the ordinary case, and a required body would answer such a call
    # with a 422 *before* the authorization check runs — telling an unauthorized
    # caller about the shape of a request they are not allowed to make, and
    # burying a permission problem under a parse error.
    payload: SheetTransitionIn | None = None,
) -> MarkSheetOut:
    """Move a mark sheet along the approval chain.

    `action` is one of submit, moderate, approve, faculty_approve,
    senate_approve, return. Each maps to its own policy target, so a head of
    department holding `results:board_approve` cannot reach the Senate step by
    calling a different URL.
    """
    sheet = get_or_404(ctx, MarkSheet, sheet_id)
    body = payload or SheetTransitionIn()
    authorize(
        engine=ctx.engine,
        action=f"mark_sheet:{action}",
        resource_type="mark_sheet",
        resource=sheet,
        category=AuditCategory.ASSESSMENT,
    )
    return MarkSheetOut.model_validate(
        service.transition_sheet(
            ctx.db,
            sheet=sheet,
            action=action,
            actor_id=ctx.principal.id,
            note=body.note,
            minute_reference=body.minute_reference,
            adjustment=body.adjustment,
        )
    )


class ReleaseIn(Schema):
    semester_id: uuid.UUID
    programme_ids: list[uuid.UUID] = Field(default_factory=list)
    scope_description: Annotated[str, Field(max_length=300)]
    minute_reference: str | None = None


@router.post("/releases", response_model=dict, status_code=status.HTTP_201_CREATED)
def release_results(payload: ReleaseIn, ctx: StaffContext) -> dict[str, Any]:
    """Publish Senate-approved results to students. MFA-gated.

    One deliberate event over a defined scope. Students compare notes within
    minutes of a release, so a partial one produces a queue at the registry
    and a reversible one produces an argument the institution loses.
    """
    authorize(
        engine=ctx.engine,
        action="results_release:publish",
        resource_type="results_release",
        resource={
            "id": None,
            "semester_id": str(payload.semester_id),
            "status": "prepared",
            "released": False,
        },
        category=AuditCategory.ASSESSMENT,
    )
    release = service.release_results(
        ctx.db,
        semester_id=payload.semester_id,
        programme_ids=payload.programme_ids,
        scope_description=payload.scope_description,
        minute_reference=payload.minute_reference,
        actor_id=ctx.principal.id,
    )
    return {
        "id": str(release.id),
        "mark_sheets": release.mark_sheet_count,
        "results": release.result_count,
        "students": release.student_count,
        "released_at": release.released_at.isoformat() if release.released_at else None,
    }


@router.get("/me/results", response_model=list[ResultRowOut])
def my_results(ctx: StudentContext, semester_id: uuid.UUID | None = None) -> list[ResultRowOut]:
    """A student's own released results.

    Filtered to `released` in the query as well as being refused by
    `assessment.student-visibility`. Two layers because an unreleased mark is
    provisional — it may still be moderated up or down — and showing one
    produces an argument that cannot be won.
    """
    stmt = select(CourseResult).where(
        CourseResult.student_id == ctx.student_id,
        CourseResult.released.is_(True),
        CourseResult.withheld.is_(False),
        CourseResult.deleted_at.is_(None),
    )
    if semester_id:
        stmt = stmt.where(CourseResult.semester_id == semester_id)
    rows = ctx.db.execute(stmt.order_by(CourseResult.course_code)).scalars().all()

    for row in rows:
        authorize(
            engine=ctx.engine,
            action="course_result:read",
            resource_type="course_result",
            resource=row,
            category=AuditCategory.ASSESSMENT,
        )
    return [ResultRowOut.model_validate(r) for r in rows]


@router.get("/students/{student_id}/transcript", response_model=dict)
def get_transcript(student_id: uuid.UUID, ctx: AnyContext) -> dict[str, Any]:
    """Build a transcript from the result rows.

    Regenerated on every request rather than stored, so it can never drift
    from the record it reports. Every read is audited — this is the most
    sensitive read in the system after the audit trail itself.
    """
    from acmis.modules.students.models import Student, StudentProgramme

    student = get_or_404(ctx, Student, student_id)
    authorize(
        engine=ctx.engine,
        action="transcript:read",
        resource_type="transcript",
        resource={"id": None, "student_id": str(student.id), "status": "issued"},
        category=AuditCategory.AWARD,
        audit_reads=True,
    )
    programme = ctx.db.execute(
        select(StudentProgramme).where(
            StudentProgramme.student_id == student.id,
            StudentProgramme.is_primary.is_(True),
        )
    ).scalar_one()
    return service.build_transcript(ctx.db, student_programme=programme)


class IssueTranscriptIn(Schema):
    kind: Annotated[str, Field(pattern="^(official|student_copy|interim|verification)$")]
    purpose: str | None = None
    recipient_name: str | None = None
    recipient_address: str | None = None


@router.post("/students/{student_id}/transcript/issue", response_model=dict)
def issue_transcript(
    student_id: uuid.UUID, payload: IssueTranscriptIn, ctx: StaffContext
) -> dict[str, Any]:
    from acmis.modules.students.models import Student, StudentProgramme

    student = get_or_404(ctx, Student, student_id)
    authorize(
        engine=ctx.engine,
        action="transcript:issue",
        resource_type="transcript",
        resource={"id": None, "student_id": str(student.id), "status": "issued"},
        category=AuditCategory.AWARD,
    )
    programme = ctx.db.execute(
        select(StudentProgramme).where(
            StudentProgramme.student_id == student.id,
            StudentProgramme.is_primary.is_(True),
        )
    ).scalar_one()
    transcript, payload_body = service.issue_transcript(
        ctx.db,
        student_programme=programme,
        kind=payload.kind,
        purpose=payload.purpose,
        recipient_name=payload.recipient_name,
        recipient_address=payload.recipient_address,
        actor_id=ctx.principal.id,
    )
    return {
        "serial_number": transcript.serial_number,
        "verification_code": transcript.verification_code,
        "issued_on": transcript.issued_on.isoformat(),
        "transcript": payload_body,
    }


class AwardOut(Schema):
    id: uuid.UUID
    student_id: uuid.UUID
    award_title: str
    award_level: str
    certificate_name: str
    classification: str | None
    final_cgpa: float | None
    credits_earned: int
    serial_number: str
    verification_code: str
    conferred_on: date
    status: str
    senate_minute_reference: str | None
    revoked_at: datetime | None


class ConferIn(Reason):
    graduation_list_id: uuid.UUID | None = None
    conferred_on: date
    minute_reference: Annotated[str, Field(min_length=3, max_length=80)]


@router.post(
    "/students/{student_id}/award", response_model=AwardOut, status_code=status.HTTP_201_CREATED
)
def confer_award(student_id: uuid.UUID, payload: ConferIn, ctx: StaffContext) -> AwardOut:
    """Confer a qualification. The system's terminal act.

    MFA-gated by `baseline.step-up-required`, blocked on an outstanding
    balance by `finance.tuition-blocks`, and requires a Senate minute
    reference. The outstanding balance is passed to the decision explicitly
    because it lives in the finance module's ledger, not on the award.
    """
    from acmis.modules.finance import service as finance
    from acmis.modules.students.models import Student, StudentProgramme

    student = get_or_404(ctx, Student, student_id)
    programme = ctx.db.execute(
        select(StudentProgramme).where(
            StudentProgramme.student_id == student.id,
            StudentProgramme.is_primary.is_(True),
        )
    ).scalar_one()

    authorize(
        engine=ctx.engine,
        action="award:confer",
        resource_type="award",
        resource={
            "id": None,
            "student_id": str(student.id),
            "status": "senate_ready",
            "outstanding_balance_minor": finance.outstanding_balance(ctx.db, student_id=student.id),
        },
        category=AuditCategory.AWARD,
    )
    award = service.confer_award(
        ctx.db,
        student_programme=programme,
        graduation_list_id=payload.graduation_list_id,
        conferred_on=payload.conferred_on,
        minute_reference=payload.minute_reference,
        actor_id=ctx.principal.id,
    )
    return AwardOut.model_validate(award)


@router.post("/awards/{award_id}/revoke", response_model=AwardOut)
def revoke_award(award_id: uuid.UUID, payload: Reason, ctx: StaffContext) -> AwardOut:
    """Revoke a conferred award.

    The row is never deleted. A revoked degree must remain visible *as
    revoked*, or the public verification endpoint cannot answer honestly about
    a certificate somebody is still holding.
    """
    from acmis.core.audit import emit
    from acmis.core.models import utcnow

    award = get_or_404(ctx, Award, award_id)
    authorize(
        engine=ctx.engine,
        action="award:revoke",
        resource_type="award",
        resource=award,
        category=AuditCategory.AWARD,
    )
    award.status = "revoked"
    award.revoked_at = utcnow()
    award.revoked_by_id = ctx.principal.id
    award.revocation_reason = payload.reason
    ctx.db.flush()
    emit(
        "award:revoke",
        AuditCategory.AWARD,
        resource_type="award",
        resource_id=award.id,
        resource_label=award.serial_number,
        summary=f"Award revoked: {payload.reason}",
        severity="critical",
    )
    return AwardOut.model_validate(award)


class GraduationListOut(Schema):
    id: uuid.UUID
    name: str
    ceremony_date: date | None
    academic_year_id: uuid.UUID
    status: str
    candidate_count: int
    excluded: list[dict[str, Any]]
    senate_approved_at: datetime | None
    senate_minute_reference: str | None


@router.get("/graduation-lists", response_model=Page[GraduationListOut])
def list_graduation_lists(ctx: StaffContext, page: PageQuery) -> Page[GraduationListOut]:
    authorize(
        engine=ctx.engine,
        action="graduation_list:list",
        resource_type="graduation_list",
        resource={"id": None, "status": "draft"},
        category=AuditCategory.AWARD,
    )
    found = keyset_page(
        ctx.db,
        select(GraduationList).where(GraduationList.deleted_at.is_(None)),
        page=page,
        key=GraduationList.ceremony_date,
        ident=GraduationList.id,
        descending=True,
        nulls="last",
    )
    return Page.of(
        [GraduationListOut.model_validate(r) for r in found.rows],
        limit=page.limit,
        next_cursor=found.next_cursor,
        total=found.total,
    )


@router.post("/semester-results/compute", response_model=dict)
def compute_semester_results(
    ctx: StaffContext, semester_id: uuid.UUID, programme_id: uuid.UUID | None = None
) -> dict[str, Any]:
    """Compute GPA, CGPA and progression for a semester.

    The outcomes are recommendations. A `discontinue` is flagged for board
    confirmation and never applied here — nobody is dismissed by a batch job.
    """
    from acmis.modules.students.models import StudentProgramme

    authorize(
        engine=ctx.engine,
        action="course_result:compute",
        resource_type="course_result",
        resource={"id": None, "semester_id": str(semester_id), "status": "senate_approved"},
        category=AuditCategory.ASSESSMENT,
    )
    stmt = select(StudentProgramme).where(
        StudentProgramme.deleted_at.is_(None), StudentProgramme.is_primary.is_(True)
    )
    if programme_id:
        stmt = stmt.where(StudentProgramme.programme_id == programme_id)
    programmes = ctx.db.execute(stmt).scalars().all()

    computed = 0
    needs_board: list[dict[str, Any]] = []
    for programme in programmes:
        row = service.compute_semester_result(
            ctx.db,
            student_programme=programme,
            semester_id=semester_id,
            actor_id=ctx.principal.id,
        )
        computed += 1
        if (row.rules_snapshot or {}).get("requires_board_confirmation"):
            needs_board.append(
                {
                    "student_id": str(programme.student_id),
                    "progression": row.progression,
                    "cgpa": float(row.cgpa) if row.cgpa else None,
                    "reasons": (row.rules_snapshot or {}).get("reasons", []),
                }
            )

    return {
        "computed": computed,
        "requiring_board_confirmation": needs_board,
    }
