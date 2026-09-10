"""Life-cycle events: special examinations, cards, transfers, time off.

Mounted separately from `students` because these are the events that happen
*to* a student rather than being part of ordinary study, and because the
student portal reaches most of them directly — applying for a special
examination and reporting a lost card are self-service, and the alternative is
a queue at the registry.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query, status
from pydantic import Field
from sqlalchemy import func, select

from acmis.core.abac import authorize
from acmis.core.audit import AuditCategory
from acmis.core.deps import AnyContext, PageQuery, StaffContext, StudentContext
from acmis.core.errors import RuleViolation
from acmis.core.pagination import keyset_page
from acmis.core.schemas import Page, Reason, RecordEnvelope, Schema
from acmis.modules.students import lifecycle
from acmis.modules.students.models import (
    ExamCard,
    InstitutionTransfer,
    Registration,
    SpecialExamRequest,
    Student,
    StudentIdCard,
)
from acmis.routers._common import get_or_404

router = APIRouter(prefix="/lifecycle", tags=["lifecycle"])


# ---------------------------------------------------------------------------
# Special and supplementary examinations
# ---------------------------------------------------------------------------


class SpecialExamOut(Schema):
    id: uuid.UUID
    reference: str
    student_id: uuid.UUID
    course_offering_id: uuid.UUID
    semester_id: uuid.UUID
    kind: str
    ground: str
    narrative: str
    missed_on: date | None
    evidence_attachment_ids: list[uuid.UUID]
    evidence_verified_at: datetime | None
    fee_minor: int | None
    status: str
    submitted_at: datetime
    recommended_at: datetime | None
    decided_at: datetime | None
    decision_note: str | None
    minute_reference: str | None
    exam_sitting_id: uuid.UUID | None
    mark_recorded: bool


class SpecialExamIn(Schema):
    course_offering_id: uuid.UUID
    semester_id: uuid.UUID
    kind: Annotated[str, Field(pattern="^(special|supplementary)$")] = "special"
    ground: Annotated[
        str,
        Field(
            pattern="^(illness|bereavement|hospitalisation|accident|national_duty"
            "|institutional_error|other)$"
        ),
    ]
    narrative: Annotated[str, Field(min_length=20, max_length=4000)]
    missed_on: date | None = None
    evidence_attachment_ids: list[uuid.UUID] = Field(default_factory=list)
    #: Set by the office when it lodges on a student's behalf.
    student_id: uuid.UUID | None = None


@router.post("/special-exams", response_model=SpecialExamOut, status_code=status.HTTP_201_CREATED)
def lodge_special_exam(payload: SpecialExamIn, ctx: AnyContext) -> SpecialExamOut:
    """Apply for a special or supplementary examination.

    Accepted without evidence — a student in hospital cannot produce a
    certificate that day — but not *granted* without it.
    """
    student_id = payload.student_id or ctx.principal.student_id
    if student_id is None:
        raise RuleViolation("Say which student this request is for.", rule="student_required")
    student = get_or_404(ctx, Student, student_id)
    authorize(
        engine=ctx.engine,
        action="special_exam_request:create",
        resource_type="special_exam_request",
        resource={
            "id": None,
            "student_id": str(student.id),
            "course_offering_id": str(payload.course_offering_id),
            "semester_id": str(payload.semester_id),
            "kind": payload.kind,
            "ground": payload.ground,
            "status": "submitted",
            "has_evidence": bool(payload.evidence_attachment_ids),
            "evidence_verified": False,
            "department_ids": [],
            "faculty_ids": [],
            "requested_by_id": str(ctx.principal.id),
        },
        category=AuditCategory.ASSESSMENT,
    )
    return SpecialExamOut.model_validate(
        lifecycle.lodge_special_exam_request(
            ctx.db,
            student=student,
            course_offering_id=payload.course_offering_id,
            semester_id=payload.semester_id,
            kind=payload.kind,
            ground=payload.ground,
            narrative=payload.narrative,
            missed_on=payload.missed_on,
            evidence_attachment_ids=payload.evidence_attachment_ids,
            actor_id=ctx.principal.id,
        )
    )


@router.get("/special-exams", response_model=Page[SpecialExamOut])
def list_special_exams(
    ctx: AnyContext,
    page: PageQuery,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    semester_id: uuid.UUID | None = None,
    mine_only: bool = False,
) -> Page[SpecialExamOut]:
    decision = authorize(
        engine=ctx.engine,
        action="special_exam_request:list",
        resource_type="special_exam_request",
        resource={
            "id": None,
            "student_id": str(ctx.principal.student_id) if ctx.principal.student_id else None,
            "course_offering_id": None,
            "semester_id": str(semester_id) if semester_id else None,
            "kind": "special",
            "ground": None,
            "status": status_filter,
            "has_evidence": True,
            "evidence_verified": True,
            "department_ids": [str(d) for d in ctx.principal.department_ids],
            "faculty_ids": [str(f) for f in ctx.principal.faculty_ids],
            "requested_by_id": None,
        },
        category=AuditCategory.ASSESSMENT,
    )
    stmt = select(SpecialExamRequest).where(SpecialExamRequest.deleted_at.is_(None))
    if status_filter:
        stmt = stmt.where(SpecialExamRequest.status == status_filter)
    if semester_id:
        stmt = stmt.where(SpecialExamRequest.semester_id == semester_id)
    # A student always sees only their own, whatever they ask for.
    if mine_only or ctx.principal.student_id is not None:
        stmt = stmt.where(SpecialExamRequest.student_id == ctx.principal.student_id)
    found = keyset_page(
        ctx.db,
        stmt,
        page=page,
        key=SpecialExamRequest.submitted_at,
        ident=SpecialExamRequest.id,
        descending=True,
    )
    items = [
        SpecialExamOut.model_construct(
            **decision.filter(SpecialExamOut.model_validate(row).model_dump())
        )
        for row in found.rows
    ]
    return Page.of(items, limit=page.limit, next_cursor=found.next_cursor, total=found.total)


@router.get("/special-exams/{request_id}", response_model=RecordEnvelope[SpecialExamOut])
def get_special_exam(request_id: uuid.UUID, ctx: AnyContext) -> RecordEnvelope[SpecialExamOut]:
    request = get_or_404(ctx, SpecialExamRequest, request_id)
    decision = authorize(
        engine=ctx.engine,
        action="special_exam_request:read",
        resource_type="special_exam_request",
        resource=request,
        category=AuditCategory.ASSESSMENT,
    )
    payload = SpecialExamOut.model_validate(request).model_dump()
    return RecordEnvelope(
        data=SpecialExamOut.model_construct(**decision.filter(payload)),
        capabilities=[],
        masked_fields=sorted(decision.masked_fields),
    )


@router.post("/special-exams/{request_id}/verify-evidence", response_model=SpecialExamOut)
def verify_evidence(request_id: uuid.UUID, ctx: StaffContext) -> SpecialExamOut:
    """Someone has seen the certificate. Separate from lodging on purpose."""
    request = get_or_404(ctx, SpecialExamRequest, request_id)
    authorize(
        engine=ctx.engine,
        action="special_exam_request:recommend",
        resource_type="special_exam_request",
        resource=request,
        category=AuditCategory.ASSESSMENT,
    )
    return SpecialExamOut.model_validate(
        lifecycle.verify_evidence(ctx.db, request=request, actor_id=ctx.principal.id)
    )


class RecommendIn(Schema):
    note: Annotated[str | None, Field(max_length=2000)] = None


@router.post("/special-exams/{request_id}/recommend", response_model=SpecialExamOut)
def recommend_special_exam(
    request_id: uuid.UUID, ctx: StaffContext, payload: RecommendIn | None = None
) -> SpecialExamOut:
    request = get_or_404(ctx, SpecialExamRequest, request_id)
    authorize(
        engine=ctx.engine,
        action="special_exam_request:recommend",
        resource_type="special_exam_request",
        resource=request,
        category=AuditCategory.ASSESSMENT,
    )
    return SpecialExamOut.model_validate(
        lifecycle.recommend_special_exam(
            ctx.db,
            request=request,
            actor_id=ctx.principal.id,
            note=(payload or RecommendIn()).note,
        )
    )


class DecideSpecialExamIn(Schema):
    grant: bool
    #: Lets the board downgrade a special request to a supplementary one,
    #: which is the difference between an uncapped mark and one capped at the
    #: pass mark. Explicit rather than inferred, because it is the most
    #: consequential field on the screen.
    kind: Annotated[str | None, Field(pattern="^(special|supplementary)$")] = None
    note: Annotated[str | None, Field(max_length=2000)] = None
    minute_reference: Annotated[str | None, Field(max_length=80)] = None


@router.post("/special-exams/{request_id}/decide", response_model=SpecialExamOut)
def decide_special_exam(
    request_id: uuid.UUID, payload: DecideSpecialExamIn, ctx: StaffContext
) -> SpecialExamOut:
    request = get_or_404(ctx, SpecialExamRequest, request_id)
    authorize(
        engine=ctx.engine,
        action="special_exam_request:decide",
        resource_type="special_exam_request",
        resource=request,
        category=AuditCategory.ASSESSMENT,
    )
    return SpecialExamOut.model_validate(
        lifecycle.decide_special_exam(
            ctx.db,
            request=request,
            grant=payload.grant,
            actor_id=ctx.principal.id,
            kind=payload.kind,
            note=payload.note,
            minute_reference=payload.minute_reference,
        )
    )


# ---------------------------------------------------------------------------
# Identity cards
# ---------------------------------------------------------------------------


class IdCardOut(Schema):
    id: uuid.UUID
    student_id: uuid.UUID
    serial: str
    barcode: str | None
    campus_id: uuid.UUID | None
    issued_on: date
    expires_on: date | None
    reason: str
    status: str
    reported_lost_on: date | None
    replacement_fee_minor: int | None
    collected_at: datetime | None


class IssueIdCardIn(Schema):
    student_id: uuid.UUID
    reason: Annotated[str, Field(pattern="^(initial|replacement|renewal|programme_change)$")] = (
        "initial"
    )
    campus_id: uuid.UUID | None = None
    photo_attachment_id: uuid.UUID | None = None
    expires_on: date | None = None
    replacement_fee_minor: Annotated[int | None, Field(ge=0)] = None


@router.post("/id-cards", response_model=IdCardOut, status_code=status.HTTP_201_CREATED)
def issue_id_card(payload: IssueIdCardIn, ctx: StaffContext) -> IdCardOut:
    student = get_or_404(ctx, Student, payload.student_id)
    authorize(
        engine=ctx.engine,
        action="student_id_card:issue",
        resource_type="student_id_card",
        resource={
            "id": None,
            "student_id": str(student.id),
            "status": "active",
            "reason": payload.reason,
            "campus_id": str(payload.campus_id) if payload.campus_id else None,
            "requested_by_id": str(ctx.principal.id),
        },
        category=AuditCategory.STUDENT_RECORD,
    )
    return IdCardOut.model_validate(
        lifecycle.issue_id_card(
            ctx.db,
            student=student,
            actor_id=ctx.principal.id,
            reason=payload.reason,
            campus_id=payload.campus_id,
            photo_attachment_id=payload.photo_attachment_id,
            expires_on=payload.expires_on,
            replacement_fee_minor=payload.replacement_fee_minor,
        )
    )


@router.get("/me/id-cards", response_model=list[IdCardOut])
def my_id_cards(ctx: StudentContext) -> list[IdCardOut]:
    rows = (
        ctx.db.execute(
            select(StudentIdCard)
            .where(
                StudentIdCard.student_id == ctx.student_id,
                StudentIdCard.deleted_at.is_(None),
            )
            .order_by(StudentIdCard.issued_on.desc())
        )
        .scalars()
        .all()
    )
    for row in rows:
        authorize(
            engine=ctx.engine,
            action="student_id_card:read",
            resource_type="student_id_card",
            resource=row,
        )
    return [IdCardOut.model_validate(row) for row in rows]


class ReportLostIn(Schema):
    stolen: bool = False


@router.post("/id-cards/{card_id}/report-lost", response_model=IdCardOut)
def report_card_lost(
    card_id: uuid.UUID, ctx: AnyContext, payload: ReportLostIn | None = None
) -> IdCardOut:
    """Block a card. Available to the student, because speed is the point.

    A card in someone else's hands opens doors; making the student wait for an
    office to open is the difference between a nuisance and an incident.
    """
    card = get_or_404(ctx, StudentIdCard, card_id)
    authorize(
        engine=ctx.engine,
        action="student_id_card:report_lost",
        resource_type="student_id_card",
        resource=card,
        category=AuditCategory.STUDENT_RECORD,
    )
    return IdCardOut.model_validate(
        lifecycle.report_card_lost(
            ctx.db,
            card=card,
            actor_id=ctx.principal.id,
            stolen=(payload or ReportLostIn()).stolen,
        )
    )


@router.get("/id-cards/verify", response_model=dict)
def verify_id_card(ctx: StaffContext, code: Annotated[str, Query(max_length=60)]) -> dict[str, Any]:
    """What a turnstile needs: is this card live, and whose is it.

    Deliberately not the student's record. A reader at a gate has no business
    with an address or a fee balance, and an endpoint that returned them would
    become the way people look those up.
    """
    authorize(
        engine=ctx.engine,
        action="student_id_card:verify",
        resource_type="student_id_card",
        resource={
            "id": None,
            "student_id": None,
            "status": "active",
            "reason": "initial",
            "campus_id": None,
            "requested_by_id": None,
        },
        category=AuditCategory.STUDENT_RECORD,
    )
    return lifecycle.verify_card(ctx.db, serial_or_barcode=code)


# ---------------------------------------------------------------------------
# Examination cards
# ---------------------------------------------------------------------------


class ExamCardOut(Schema):
    id: uuid.UUID
    student_id: uuid.UUID
    registration_id: uuid.UUID
    semester_id: uuid.UUID
    verification_code: str
    session: str
    issued_at: datetime
    valid_until: date | None
    course_offering_ids: list[uuid.UUID]
    clearance_snapshot: dict[str, Any]
    override_reason: str | None
    status: str


class IssueExamCardIn(Schema):
    registration_id: uuid.UUID
    session: Annotated[str, Field(pattern="^(main|supplementary|special)$")] = "main"
    #: Named and recorded. Hardship is real, and a system with no override
    #: gets one anyway — informally, at the counter, unrecorded.
    override_reason: Annotated[str | None, Field(min_length=10, max_length=1000)] = None


@router.post("/exam-cards", response_model=ExamCardOut, status_code=status.HTTP_201_CREATED)
def issue_exam_card(payload: IssueExamCardIn, ctx: StaffContext) -> ExamCardOut:
    """Issue permission to sit, recording the gates as they stood."""
    from acmis.modules.finance import service as finance
    from acmis.modules.quality import service as quality

    registration = get_or_404(ctx, Registration, payload.registration_id)
    percentage, required = finance.fee_percentage_paid(
        ctx.db,
        student_id=registration.student_id,
        semester_id=registration.semester_id,
    )

    # Attendance is a gate only where the institution keeps registers for the
    # courses on this registration. No registers means no opinion, not a fail.
    attendance_ok: bool | None = None
    offering_ids = [
        row.course_offering_id for row in registration.courses if row.deleted_at is None
    ]
    if offering_ids:
        shortfalls = 0
        measured = 0
        for offering_id in offering_ids:
            for row in quality.attendance_for_offering(ctx.db, course_offering_id=offering_id):
                if row["student_id"] != str(registration.student_id):
                    continue
                if row["percentage"] is None:
                    continue
                measured += 1
                if row["percentage"] < 75:
                    shortfalls += 1
        if measured:
            attendance_ok = shortfalls == 0

    authorize(
        engine=ctx.engine,
        action="exam_card:issue",
        resource_type="exam_card",
        resource={
            "id": None,
            "student_id": str(registration.student_id),
            "registration_id": str(registration.id),
            "semester_id": str(registration.semester_id),
            "session": payload.session,
            "status": "issued",
            "fee_percentage_paid": percentage,
            "required_percentage": required,
            "attendance_ok": attendance_ok,
        },
        category=AuditCategory.ASSESSMENT,
    )
    return ExamCardOut.model_validate(
        lifecycle.issue_exam_card(
            ctx.db,
            registration=registration,
            actor_id=ctx.principal.id,
            fee_percentage_paid=percentage,
            required_percentage=float(required),
            attendance_ok=attendance_ok,
            session_name=payload.session,
            override_reason=payload.override_reason,
        )
    )


class ExamCardPaperOut(Schema):
    course_offering_id: uuid.UUID
    code: str
    title: str


class MyExamCardOut(ExamCardOut):
    """The card as the candidate needs to read it.

    The stored row holds offering ids and a semester id, which are the right
    keys and the wrong thing to print on a card someone carries into a hall.
    Resolved here rather than in the portal: the papers a card admits you to
    are part of the card, not a lookup the client should have to make.
    """

    semester_name: str | None = None
    papers: list[ExamCardPaperOut] = Field(default_factory=list)


@router.get("/me/exam-cards", response_model=list[MyExamCardOut])
def my_exam_cards(ctx: StudentContext) -> list[MyExamCardOut]:
    from acmis.modules.curriculum.models import Course, CourseOffering
    from acmis.modules.shared.models import Semester

    rows = (
        ctx.db.execute(
            select(ExamCard)
            .where(ExamCard.student_id == ctx.student_id, ExamCard.deleted_at.is_(None))
            .order_by(ExamCard.issued_at.desc())
        )
        .scalars()
        .all()
    )
    for row in rows:
        authorize(
            engine=ctx.engine,
            action="exam_card:read",
            resource_type="exam_card",
            resource=row,
        )

    offering_ids = {oid for row in rows for oid in row.course_offering_ids}
    papers: dict[uuid.UUID, ExamCardPaperOut] = {}
    if offering_ids:
        for offering_id, code, title in ctx.db.execute(
            select(CourseOffering.id, Course.code, Course.title)
            .join(Course, Course.id == CourseOffering.course_id)
            .where(CourseOffering.id.in_(list(offering_ids)))
        ).all():
            papers[offering_id] = ExamCardPaperOut(
                course_offering_id=offering_id, code=str(code), title=str(title)
            )

    semester_ids = {row.semester_id for row in rows}
    names: dict[uuid.UUID, str] = {}
    if semester_ids:
        for semester_id, name in ctx.db.execute(
            select(Semester.id, Semester.name).where(Semester.id.in_(list(semester_ids)))
        ).all():
            names[semester_id] = str(name)

    out: list[MyExamCardOut] = []
    for row in rows:
        card = MyExamCardOut.model_validate(row)
        card.semester_name = names.get(row.semester_id)
        card.papers = sorted(
            (papers[oid] for oid in row.course_offering_ids if oid in papers),
            key=lambda paper: paper.code,
        )
        out.append(card)
    return out


@router.get("/exam-cards/verify", response_model=dict)
def verify_exam_card(
    ctx: StaffContext, code: Annotated[str, Query(max_length=40)]
) -> dict[str, Any]:
    """What an invigilator at the hall door needs."""
    authorize(
        engine=ctx.engine,
        action="exam_card:verify",
        resource_type="exam_card",
        resource={
            "id": None,
            "student_id": None,
            "registration_id": None,
            "semester_id": None,
            "session": "main",
            "status": "issued",
            "fee_percentage_paid": None,
            "required_percentage": None,
            "attendance_ok": None,
        },
        category=AuditCategory.ASSESSMENT,
    )
    return lifecycle.verify_exam_card(ctx.db, code=code)


@router.post("/exam-cards/{card_id}/revoke", response_model=ExamCardOut)
def revoke_exam_card(card_id: uuid.UUID, payload: Reason, ctx: StaffContext) -> ExamCardOut:
    card = get_or_404(ctx, ExamCard, card_id)
    authorize(
        engine=ctx.engine,
        action="exam_card:revoke",
        resource_type="exam_card",
        resource=card,
        category=AuditCategory.ASSESSMENT,
    )
    return ExamCardOut.model_validate(
        lifecycle.revoke_exam_card(
            ctx.db, card=card, reason=payload.reason, actor_id=ctx.principal.id
        )
    )


# ---------------------------------------------------------------------------
# Time off
# ---------------------------------------------------------------------------


@router.get("/me/time-off", response_model=dict)
def my_time_off(ctx: StudentContext) -> dict[str, Any]:
    """How much time off a student has had, and how much room is left.

    Read from the approved status changes and measured against the
    programme's duration rules, so a student can see the ceiling before they
    hit it.
    """
    from acmis.modules.assessment.rules import DEFAULT_PROGRESSION_RULES, study_duration
    from acmis.modules.students.models import Enrolment, StudentProgramme

    taken = lifecycle.time_off_taken(ctx.db, student_id=ctx.student_id)
    enrolled = int(
        ctx.db.execute(
            select(func.count()).where(
                Enrolment.student_id == ctx.student_id, Enrolment.deleted_at.is_(None)
            )
        ).scalar_one()
    )
    programme = (
        ctx.db.execute(
            select(StudentProgramme).where(
                StudentProgramme.student_id == ctx.student_id,
                StudentProgramme.is_primary.is_(True),
                StudentProgramme.deleted_at.is_(None),
            )
        )
        .scalars()
        .first()
    )

    # From the programme where it is known. The fallback of six is a
    # three-year undergraduate degree — the commonest shape, and it errs
    # towards a *shorter* permitted duration, so the answer is conservative
    # rather than reassuring.
    normal_semesters = 6
    if programme is not None:
        from acmis.modules.curriculum.models import Programme

        row = ctx.db.get(Programme, programme.programme_id)
        if row is not None and row.duration_semesters:
            normal_semesters = int(row.duration_semesters)

    verdict = study_duration(
        normal_semesters=normal_semesters,
        semesters_enrolled=enrolled,
        dead_semesters=taken["dead_semesters"],
        rules=DEFAULT_PROGRESSION_RULES,
    )
    return {
        **taken,
        "semesters_enrolled": verdict.semesters_used,
        "semesters_permitted": verdict.semesters_permitted,
        "dead_semesters_permitted": verdict.dead_semesters_permitted,
        "standing": verdict.standing,
        "reason": verdict.reason,
        "programme_id": str(programme.programme_id) if programme is not None else None,
    }


# ---------------------------------------------------------------------------
# Transfers between institutions
# ---------------------------------------------------------------------------


class TransferOut(Schema):
    id: uuid.UUID
    reference: str
    direction: str
    student_id: uuid.UUID | None
    applicant_id: uuid.UUID | None
    other_institution_name: str
    other_institution_country: str
    other_programme_name: str | None
    programme_id: uuid.UUID | None
    entry_year_of_study: int | None
    credit_assessment: list[dict[str, Any]]
    credits_claimed: int
    credits_awarded: int
    credit_transfer_cap_percent: int | None
    status: str
    requested_at: datetime
    approved_at: datetime | None
    transcript_issued_at: datetime | None
    senate_minute_reference: str | None


class TransferIn(Schema):
    direction: Annotated[str, Field(pattern="^(incoming|outgoing)$")]
    other_institution_name: Annotated[str, Field(max_length=200)]
    other_institution_country: Annotated[str, Field(max_length=2)] = "UG"
    other_institution_regulator_code: Annotated[str | None, Field(max_length=40)] = None
    other_programme_name: Annotated[str | None, Field(max_length=200)] = None
    student_id: uuid.UUID | None = None
    applicant_id: uuid.UUID | None = None
    programme_id: uuid.UUID | None = None
    curriculum_version_id: uuid.UUID | None = None
    effective_semester_id: uuid.UUID | None = None
    entry_year_of_study: Annotated[int | None, Field(ge=1, le=12)] = None
    credits_claimed: Annotated[int, Field(ge=0, le=1000)] = 0
    credit_transfer_cap_percent: Annotated[int | None, Field(ge=0, le=100)] = None
    evidence_attachment_ids: list[uuid.UUID] = Field(default_factory=list)


@router.post("/transfers", response_model=TransferOut, status_code=status.HTTP_201_CREATED)
def lodge_transfer(payload: TransferIn, ctx: AnyContext) -> TransferOut:
    """Open a transfer in either direction."""
    student_id = payload.student_id or (
        ctx.principal.student_id if payload.direction == "outgoing" else None
    )
    authorize(
        engine=ctx.engine,
        action="institution_transfer:create",
        resource_type="institution_transfer",
        resource={
            "id": None,
            "direction": payload.direction,
            "student_id": str(student_id) if student_id else None,
            "applicant_id": str(payload.applicant_id) if payload.applicant_id else None,
            "programme_id": str(payload.programme_id) if payload.programme_id else None,
            "status": "requested",
            "credits_claimed": payload.credits_claimed,
            "credits_awarded": 0,
            "credit_transfer_cap_percent": payload.credit_transfer_cap_percent,
            "requested_by_id": str(ctx.principal.id),
        },
        category=AuditCategory.STUDENT_RECORD,
    )
    data = payload.model_dump()
    data["student_id"] = student_id
    return TransferOut.model_validate(
        lifecycle.lodge_institution_transfer(ctx.db, actor_id=ctx.principal.id, **data)
    )


@router.get("/me/transfers", response_model=list[TransferOut])
def my_transfers(ctx: StudentContext) -> list[TransferOut]:
    """A student's own transfers out.

    Separate from `/transfers`, which is staff-only, because a student cannot
    be given the class-level list: the decision for "every transfer" cannot
    conclude that the rows belong to the caller, and pretending it can is the
    bug that leaks a register. Scoped by the caller's own id here instead, so
    the rule that permits an outgoing transfer to its own student applies.
    """
    authorize(
        engine=ctx.engine,
        action="institution_transfer:list",
        resource_type="institution_transfer",
        resource={
            "id": None,
            "direction": "outgoing",
            "student_id": str(ctx.student_id),
            "applicant_id": None,
            "programme_id": None,
            "status": "requested",
            "credits_claimed": 0,
            "credits_awarded": 0,
            "credit_transfer_cap_percent": None,
            "requested_by_id": str(ctx.principal.id),
        },
        category=AuditCategory.STUDENT_RECORD,
    )
    rows = ctx.db.scalars(
        select(InstitutionTransfer)
        .where(
            InstitutionTransfer.student_id == ctx.student_id,
            InstitutionTransfer.deleted_at.is_(None),
        )
        .order_by(InstitutionTransfer.requested_at.desc())
    ).all()
    return [TransferOut.model_validate(row) for row in rows]


@router.get("/transfers", response_model=Page[TransferOut])
def list_transfers(
    ctx: StaffContext,
    page: PageQuery,
    direction: Annotated[str | None, Query(pattern="^(incoming|outgoing)$")] = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
) -> Page[TransferOut]:
    authorize(
        engine=ctx.engine,
        action="institution_transfer:list",
        resource_type="institution_transfer",
        resource={
            "id": None,
            "direction": direction or "incoming",
            "student_id": None,
            "applicant_id": None,
            "programme_id": None,
            "status": status_filter,
            "credits_claimed": 0,
            "credits_awarded": 0,
            "credit_transfer_cap_percent": None,
            "requested_by_id": None,
        },
        category=AuditCategory.STUDENT_RECORD,
    )
    stmt = select(InstitutionTransfer).where(InstitutionTransfer.deleted_at.is_(None))
    if direction:
        stmt = stmt.where(InstitutionTransfer.direction == direction)
    if status_filter:
        stmt = stmt.where(InstitutionTransfer.status == status_filter)
    found = keyset_page(
        ctx.db,
        stmt,
        page=page,
        key=InstitutionTransfer.requested_at,
        ident=InstitutionTransfer.id,
        descending=True,
    )
    return Page.of(
        [TransferOut.model_validate(row) for row in found.rows],
        limit=page.limit,
        next_cursor=found.next_cursor,
        total=found.total,
    )


class AssessTransferIn(Schema):
    #: [{external_code, external_title, external_credits, external_grade,
    #:   course_id, credits_awarded, decision: accepted|rejected, note}]
    assessment: Annotated[list[dict[str, Any]], Field(min_length=1, max_length=200)]
    total_programme_credits: Annotated[int | None, Field(ge=1)] = None


@router.post("/transfers/{transfer_id}/assess", response_model=TransferOut)
def assess_transfer(
    transfer_id: uuid.UUID, payload: AssessTransferIn, ctx: StaffContext
) -> TransferOut:
    """Record the course-by-course judgement, and check it against the cap."""
    transfer = get_or_404(ctx, InstitutionTransfer, transfer_id)
    authorize(
        engine=ctx.engine,
        action="institution_transfer:assess",
        resource_type="institution_transfer",
        resource=transfer,
        category=AuditCategory.CURRICULUM,
    )
    return TransferOut.model_validate(
        lifecycle.assess_transfer_credit(
            ctx.db,
            transfer=transfer,
            assessment=payload.assessment,
            actor_id=ctx.principal.id,
            total_programme_credits=payload.total_programme_credits,
        )
    )


class ApproveTransferIn(Schema):
    minute_reference: Annotated[str | None, Field(max_length=80)] = None
    note: Annotated[str | None, Field(max_length=2000)] = None


@router.post("/transfers/{transfer_id}/approve", response_model=TransferOut)
def approve_transfer(
    transfer_id: uuid.UUID, ctx: StaffContext, payload: ApproveTransferIn | None = None
) -> TransferOut:
    transfer = get_or_404(ctx, InstitutionTransfer, transfer_id)
    authorize(
        engine=ctx.engine,
        action="institution_transfer:approve",
        resource_type="institution_transfer",
        resource=transfer,
        category=AuditCategory.STUDENT_RECORD,
    )
    body = payload or ApproveTransferIn()
    return TransferOut.model_validate(
        lifecycle.approve_transfer(
            ctx.db,
            transfer=transfer,
            actor_id=ctx.principal.id,
            minute_reference=body.minute_reference,
            note=body.note,
        )
    )


@router.post("/transfers/{transfer_id}/issue-papers", response_model=TransferOut)
def issue_transfer_papers(transfer_id: uuid.UUID, ctx: StaffContext) -> TransferOut:
    """The transcript and the letter of good standing for a student leaving."""
    transfer = get_or_404(ctx, InstitutionTransfer, transfer_id)
    authorize(
        engine=ctx.engine,
        action="institution_transfer:issue_papers",
        resource_type="institution_transfer",
        resource=transfer,
        category=AuditCategory.AWARD,
    )
    return TransferOut.model_validate(
        lifecycle.issue_outgoing_papers(ctx.db, transfer=transfer, actor_id=ctx.principal.id)
    )
