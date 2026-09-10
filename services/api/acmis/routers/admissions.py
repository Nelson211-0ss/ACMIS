"""Admissions and enrolment endpoints."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query, status
from pydantic import Field
from sqlalchemy import func, select

from acmis.core.abac import authorize, enforce_writable
from acmis.core.audit import AuditCategory, diff, emit
from acmis.core.deps import AnyContext, ApplicantContext, PageQuery, StaffContext
from acmis.core.errors import Conflict, NotFound, RuleViolation
from acmis.core.models import utcnow
from acmis.core.pagination import keyset_page
from acmis.core.schemas import Page, Reason, RecordEnvelope, Schema
from acmis.modules.admissions import service
from acmis.modules.admissions.models import (
    AdmissionScheme,
    Applicant,
    Application,
    Offer,
    ProgrammeIntake,
    SelectionList,
)

router = APIRouter(prefix="/admissions", tags=["admissions"])


# ---------------------------------------------------------------------------
# Schemes and intakes
# ---------------------------------------------------------------------------


class SchemeOut(Schema):
    id: uuid.UUID
    code: str
    name: str
    description: str | None
    entry_scheme: str
    study_level: str
    opens_at: datetime
    closes_at: datetime
    late_closes_at: datetime | None
    results_due_on: date | None
    acceptance_deadline_on: date | None
    application_fee_minor: int
    currency: str
    max_programme_choices: int
    requires_interview: bool
    status: str


class SchemeIn(Schema):
    code: Annotated[str, Field(max_length=40)]
    name: Annotated[str, Field(max_length=200)]
    description: str | None = None
    academic_year_id: uuid.UUID
    entry_scheme: str = "private"
    study_level: str = "undergraduate"
    opens_at: datetime
    closes_at: datetime
    late_closes_at: datetime | None = None
    application_fee_minor: int = 0
    late_fee_minor: int = 0
    max_programme_choices: Annotated[int, Field(ge=1, le=12)] = 6
    requires_interview: bool = False
    requires_entrance_exam: bool = False
    scoring_weights: dict[str, Any] = Field(default_factory=dict)


@router.get("/schemes", response_model=Page[SchemeOut])
def list_schemes(
    ctx: AnyContext,
    page: PageQuery,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
) -> Page[SchemeOut]:
    authorize(
        engine=ctx.engine,
        action="admission_scheme:list",
        resource_type="admission_scheme",
        resource={"id": None, "status": status_filter},
    )
    stmt = select(AdmissionScheme).where(AdmissionScheme.deleted_at.is_(None))
    if status_filter:
        stmt = stmt.where(AdmissionScheme.status == status_filter)
    found = keyset_page(
        ctx.db,
        stmt,
        page=page,
        key=AdmissionScheme.opens_at,
        ident=AdmissionScheme.id,
        descending=True,
    )
    return Page.of(
        [SchemeOut.model_validate(r) for r in found.rows],
        limit=page.limit,
        next_cursor=found.next_cursor,
        total=found.total,
    )


@router.post("/schemes", response_model=SchemeOut, status_code=status.HTTP_201_CREATED)
def create_scheme(payload: SchemeIn, ctx: StaffContext) -> SchemeOut:
    authorize(
        engine=ctx.engine,
        action="admission_scheme:create",
        resource_type="admission_scheme",
        resource={"id": None, "status": "draft"},
        category=AuditCategory.ADMISSION,
    )
    scheme = AdmissionScheme(
        **payload.model_dump(),
        currency=ctx.tenant.currency,
        created_by_id=ctx.principal.id,
    )
    ctx.db.add(scheme)
    ctx.db.flush()
    emit(
        "admission_scheme:create",
        AuditCategory.ADMISSION,
        resource_type="admission_scheme",
        resource_id=scheme.id,
        resource_label=f"{scheme.code} — {scheme.name}",
        summary=f"Created admission scheme {scheme.code}",
    )
    return SchemeOut.model_validate(scheme)


@router.post("/schemes/{scheme_id}/publish", response_model=SchemeOut)
def publish_scheme(scheme_id: uuid.UUID, ctx: StaffContext) -> SchemeOut:
    """Open a scheme to applicants.

    The point of no return for a cycle: once applicants can see it, its fee,
    its deadline and its programme list are commitments. Hence a separate,
    separately-authorized action rather than an editable status field.
    """
    scheme = _get(ctx, AdmissionScheme, scheme_id)
    authorize(
        engine=ctx.engine,
        action="admission_scheme:publish",
        resource_type="admission_scheme",
        resource=scheme,
        category=AuditCategory.ADMISSION,
    )
    if scheme.status != "draft":
        raise Conflict("Only a draft scheme can be published.")
    if not ctx.db.execute(
        select(func.count())
        .select_from(ProgrammeIntake)
        .where(ProgrammeIntake.scheme_id == scheme.id, ProgrammeIntake.deleted_at.is_(None))
    ).scalar_one():
        raise RuleViolation(
            "A scheme cannot be published with no programme intakes — applicants "
            "would have nothing to apply for.",
            rule="scheme_requires_intakes",
        )

    before = {"status": scheme.status}
    scheme.status = "open"
    scheme.published_at = utcnow()
    scheme.published_by_id = ctx.principal.id
    emit(
        "admission_scheme:publish",
        AuditCategory.ADMISSION,
        resource_type="admission_scheme",
        resource_id=scheme.id,
        resource_label=scheme.code,
        summary=f"Published {scheme.code}; applications open until {scheme.closes_at:%d %b %Y}",
        changes=diff(before, {"status": scheme.status}),
        severity="notice",
    )
    return SchemeOut.model_validate(scheme)


# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------


class ApplicationOut(Schema):
    id: uuid.UUID
    number: str
    applicant_id: uuid.UUID
    scheme_id: uuid.UUID
    status: str
    submitted_at: datetime | None
    is_late: bool
    fee_settled_at: datetime | None
    aggregate_score: float | None
    final_score: float | None
    waitlist_position: int | None
    decided_at: datetime | None
    decision_reason: str | None
    flags: list[str]
    created_at: datetime
    updated_at: datetime


class ApplicantSummary(Schema):
    id: uuid.UUID
    reference: str
    surname: str
    given_names: str
    other_names: str | None
    date_of_birth: date
    sex: str
    nationality: str
    district_of_origin: str | None
    email: str
    phone: str
    #: Masked for most readers. Present as a key with a null value would imply
    #: "not recorded"; the field is dropped entirely, and `masked_fields` on
    #: the envelope names it.
    national_id: str | None = None
    disability: str | None = None
    disability_detail: str | None = None


class ApplicationDetail(ApplicationOut):
    applicant: ApplicantSummary
    choices: list[dict[str, Any]]


@router.get("/applications", response_model=Page[ApplicationOut])
def list_applications(
    ctx: StaffContext,
    page: PageQuery,
    scheme_id: uuid.UUID | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    faculty_id: uuid.UUID | None = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> Page[ApplicationOut]:
    """List applications the caller may see.

    The ABAC decision is taken once for the *class*, and then the query is
    narrowed to the caller's own faculties. Both are needed: the policy decides
    whether they may review at all, and the narrowing keeps a dean out of
    another faculty's intake without relying on them not to pass a
    `faculty_id` they were not granted.
    """
    decision = authorize(
        engine=ctx.engine,
        action="application:list",
        resource_type="application",
        resource={"id": None, "status": status_filter},
        category=AuditCategory.ADMISSION,
    )

    stmt = select(Application).where(Application.deleted_at.is_(None))
    if scheme_id:
        stmt = stmt.where(Application.scheme_id == scheme_id)
    if status_filter:
        stmt = stmt.where(Application.status == status_filter)

    reach = ctx.principal.faculty_ids
    if reach and "admissions:process" not in ctx.principal.permissions:
        # A reviewer without the office-wide grant sees only applications
        # ranked to their own faculties.
        wanted = [faculty_id] if faculty_id and faculty_id in reach else sorted(reach)
        stmt = stmt.where(Application.faculty_ids.overlap(wanted))
    elif faculty_id:
        stmt = stmt.where(Application.faculty_ids.overlap([faculty_id]))

    if search:
        term = f"%{search.lower()}%"
        stmt = stmt.join(Applicant).where(
            func.lower(Applicant.surname).like(term)
            | func.lower(Applicant.given_names).like(term)
            | func.lower(Application.number).like(term)
        )

    # Ranked highest first, with the unscored at the end: an officer works down
    # the merit order, and an unscored application has no place in it yet.
    found = keyset_page(
        ctx.db,
        stmt,
        page=page,
        key=Application.final_score,
        ident=Application.id,
        descending=True,
        nulls="last",
    )

    items = [ApplicationOut.model_validate(r) for r in found.rows]
    if decision.masked_fields:
        items = [ApplicationOut.model_construct(**decision.filter(i.model_dump())) for i in items]
    return Page.of(items, limit=page.limit, next_cursor=found.next_cursor, total=found.total)


@router.get("/applications/{application_id}", response_model=RecordEnvelope[ApplicationDetail])
def get_application(
    application_id: uuid.UUID, ctx: AnyContext
) -> RecordEnvelope[ApplicationDetail]:
    application = _get(ctx, Application, application_id)
    decision = authorize(
        engine=ctx.engine,
        action="application:read",
        resource_type="application",
        resource=application,
        category=AuditCategory.ADMISSION,
    )

    applicant_data = ApplicantSummary.model_validate(application.applicant).model_dump()
    payload = ApplicationDetail.model_construct(
        **ApplicationOut.model_validate(application).model_dump(),
        applicant=ApplicantSummary.model_construct(**decision.filter(applicant_data)),
        choices=[
            {
                "id": str(c.id),
                "rank": c.rank,
                "programme_intake_id": str(c.programme_intake_id),
                "is_eligible": c.is_eligible,
                "ineligibility_reasons": c.ineligibility_reasons,
                "outcome": c.outcome,
            }
            for c in application.choices
        ],
    )
    return RecordEnvelope(
        data=payload,
        capabilities=service.capabilities_for(ctx, application),
        masked_fields=sorted(decision.masked_fields),
    )


class ApplicationCreateIn(Schema):
    scheme_id: uuid.UUID
    #: Ranked programme intakes, best first.
    programme_intake_ids: Annotated[list[uuid.UUID], Field(min_length=1, max_length=12)]


@router.post("/applications", response_model=ApplicationOut, status_code=status.HTTP_201_CREATED)
def start_application(payload: ApplicationCreateIn, ctx: ApplicantContext) -> ApplicationOut:
    authorize(
        engine=ctx.engine,
        action="application:create",
        resource_type="application",
        resource={"id": None, "applicant_id": str(ctx.applicant_id), "status": "draft"},
        category=AuditCategory.ADMISSION,
    )
    application = service.start_application(
        ctx.db,
        applicant_id=ctx.applicant_id,
        scheme_id=payload.scheme_id,
        programme_intake_ids=payload.programme_intake_ids,
        actor_id=ctx.principal.id,
    )
    return ApplicationOut.model_validate(application)


class ApplicationUpdateIn(Schema):
    programme_intake_ids: list[uuid.UUID] | None = None
    review_notes: str | None = None
    flags: list[str] | None = None


@router.patch("/applications/{application_id}", response_model=ApplicationOut)
def update_application(
    application_id: uuid.UUID, payload: ApplicationUpdateIn, ctx: AnyContext
) -> ApplicationOut:
    application = _get(ctx, Application, application_id)
    decision = authorize(
        engine=ctx.engine,
        action="application:update",
        resource_type="application",
        resource=application,
        category=AuditCategory.ADMISSION,
    )
    # The field-level half of the decision. Without this line an applicant
    # with a legitimate `application:update` grant on their own draft could
    # also write `flags` and `review_notes`, which are the office's.
    enforce_writable(decision, payload.model_dump(exclude_unset=True))

    return ApplicationOut.model_validate(
        service.update_application(
            ctx.db,
            application=application,
            changes=payload.model_dump(exclude_unset=True),
            actor_id=ctx.principal.id,
        )
    )


@router.post("/applications/{application_id}/submit", response_model=ApplicationOut)
def submit_application(application_id: uuid.UUID, ctx: ApplicantContext) -> ApplicationOut:
    application = _get(ctx, Application, application_id)
    authorize(
        engine=ctx.engine,
        action="application:submit",
        resource_type="application",
        resource=application,
        category=AuditCategory.ADMISSION,
    )
    return ApplicationOut.model_validate(
        service.submit_application(ctx.db, application=application, actor_id=ctx.principal.id)
    )


class ScoreIn(Schema):
    interview_score: float | None = None
    entrance_exam_score: float | None = None


@router.post("/applications/{application_id}/score", response_model=ApplicationOut)
def score_application(
    application_id: uuid.UUID, payload: ScoreIn, ctx: StaffContext
) -> ApplicationOut:
    application = _get(ctx, Application, application_id)
    authorize(
        engine=ctx.engine,
        action="application:score",
        resource_type="application",
        resource=application,
        category=AuditCategory.ADMISSION,
    )
    return ApplicationOut.model_validate(
        service.score_application(
            ctx.db,
            application=application,
            interview_score=payload.interview_score,
            entrance_exam_score=payload.entrance_exam_score,
            actor_id=ctx.principal.id,
        )
    )


# ---------------------------------------------------------------------------
# Selection and offers
# ---------------------------------------------------------------------------


class SelectionGenerateIn(Schema):
    scheme_id: uuid.UUID
    programme_intake_id: uuid.UUID | None = None
    name: Annotated[str, Field(max_length=200)]
    method: str = "merit"
    #: Admit down to this score, or until the intake fills — whichever binds
    #: first. Both, because a hard cut-off with unfilled seats and a filled
    #: intake with unqualified candidates are both wrong.
    minimum_score: float | None = None
    round_number: int = 1


class SelectionListOut(Schema):
    id: uuid.UUID
    name: str
    scheme_id: uuid.UUID
    programme_intake_id: uuid.UUID | None
    round_number: int
    status: str
    method: str
    cutoff_score: float | None
    admitted_count: int
    waitlisted_count: int
    rejected_count: int
    prepared_by_id: uuid.UUID | None
    approved_by_id: uuid.UUID | None
    approved_at: datetime | None
    published_at: datetime | None


@router.post(
    "/selection-lists", response_model=SelectionListOut, status_code=status.HTTP_201_CREATED
)
def generate_selection_list(payload: SelectionGenerateIn, ctx: StaffContext) -> SelectionListOut:
    """Rank the eligible applications and propose a list.

    Proposes. Nothing is admitted until the list is approved by someone else,
    and the ranking snapshot is kept on the row so a disputed selection can be
    replayed exactly.
    """
    authorize(
        engine=ctx.engine,
        action="selection_list:create",
        resource_type="selection_list",
        resource={"id": None, "status": "draft", "scheme_id": str(payload.scheme_id)},
        category=AuditCategory.ADMISSION,
    )
    return SelectionListOut.model_validate(
        service.generate_selection_list(
            ctx.db,
            scheme_id=payload.scheme_id,
            programme_intake_id=payload.programme_intake_id,
            name=payload.name,
            method=payload.method,
            minimum_score=payload.minimum_score,
            round_number=payload.round_number,
            actor_id=ctx.principal.id,
        )
    )


@router.post("/selection-lists/{list_id}/approve", response_model=SelectionListOut)
def approve_selection_list(
    list_id: uuid.UUID, payload: Reason, ctx: StaffContext
) -> SelectionListOut:
    selection = _get(ctx, SelectionList, list_id)
    authorize(
        engine=ctx.engine,
        action="selection_list:approve",
        resource_type="selection_list",
        resource=selection,
        category=AuditCategory.ADMISSION,
    )
    return SelectionListOut.model_validate(
        service.approve_selection_list(
            ctx.db, selection=selection, actor_id=ctx.principal.id, reason=payload.reason
        )
    )


class OfferOut(Schema):
    id: uuid.UUID
    application_id: uuid.UUID
    reference: str
    status: str
    condition: str | None
    sponsorship: str
    tuition_per_semester_minor: int
    issued_at: datetime
    respond_by: date
    responded_at: datetime | None


@router.post(
    "/selection-lists/{list_id}/issue-offers",
    response_model=dict,
    status_code=status.HTTP_202_ACCEPTED,
)
def issue_offers(list_id: uuid.UUID, ctx: StaffContext) -> dict[str, Any]:
    """Issue offers for an approved list.

    Each offer is authorized individually against the intake's approved
    capacity, so a list that would over-admit fails on the offer that breaches
    the ceiling rather than silently exceeding it — and the failure names the
    programme.
    """
    selection = _get(ctx, SelectionList, list_id)
    authorize(
        engine=ctx.engine,
        action="offer:issue",
        resource_type="selection_list",
        resource=selection,
        category=AuditCategory.ADMISSION,
    )
    return service.issue_offers(
        ctx.db, selection=selection, engine=ctx.engine, actor_id=ctx.principal.id
    )


class OfferResponseIn(Schema):
    accept: bool
    decline_reason: Annotated[str | None, Field(max_length=300)] = None


@router.post("/offers/{offer_id}/respond", response_model=OfferOut)
def respond_to_offer(
    offer_id: uuid.UUID, payload: OfferResponseIn, ctx: ApplicantContext
) -> OfferOut:
    offer = _get(ctx, Offer, offer_id)
    authorize(
        engine=ctx.engine,
        action="offer:respond",
        resource_type="offer",
        resource=offer,
        category=AuditCategory.ADMISSION,
    )
    return OfferOut.model_validate(
        service.respond_to_offer(
            ctx.db,
            offer=offer,
            accept=payload.accept,
            decline_reason=payload.decline_reason,
            actor_id=ctx.principal.id,
        )
    )


class EnrolIn(Schema):
    student_number: Annotated[str | None, Field(max_length=30)] = None
    semester_id: uuid.UUID


@router.post("/offers/{offer_id}/enrol", response_model=dict)
def enrol_applicant(offer_id: uuid.UUID, payload: EnrolIn, ctx: StaffContext) -> dict[str, Any]:
    """Turn an accepted offer into a student. The module's terminal act.

    Creates the student, their programme attachment, their first enrolment and
    their opening invoice in one transaction. Everything or nothing: a student
    record with no enrolment, or an enrolment with no invoice, is a state the
    registry then has to repair by hand.
    """
    offer = _get(ctx, Offer, offer_id)
    authorize(
        engine=ctx.engine,
        action="enrolment:create",
        resource_type="offer",
        resource=offer,
        category=AuditCategory.ENROLMENT,
    )
    return service.enrol(
        ctx.db,
        offer=offer,
        semester_id=payload.semester_id,
        student_number=payload.student_number,
        actor_id=ctx.principal.id,
    )


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@router.get("/schemes/{scheme_id}/statistics", response_model=dict)
def scheme_statistics(scheme_id: uuid.UUID, ctx: StaffContext) -> dict[str, Any]:
    scheme = _get(ctx, AdmissionScheme, scheme_id)
    authorize(
        engine=ctx.engine,
        action="admission_scheme:read",
        resource_type="admission_scheme",
        resource=scheme,
    )
    return service.scheme_statistics(ctx.db, scheme=scheme)


def _get(ctx: Any, model: Any, record_id: uuid.UUID) -> Any:
    """Load a record or 404.

    Loads before authorizing, deliberately: most rules read the record's own
    attributes, so there is nothing to decide until it is in hand. The 404 is
    raised before any authorization, which does leak existence — acceptable
    here because these ids are opaque UUIDs that only come from a list the
    caller was already permitted to see.
    """
    row = ctx.db.get(model, record_id)
    if row is None or getattr(row, "deleted_at", None) is not None:
        raise NotFound()
    return row
