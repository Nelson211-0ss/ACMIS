"""Standards endpoints: LTI 1.3 Advantage, OneRoster 1.2, QTI.

Mounted at the paths the standards specify, not under `/api/v1`. That is not a
detail — a conforming OneRoster consumer constructs
`/ims/oneroster/rostering/v1p2/users` and an LTI tool is configured with a
JWKS URL, and putting either behind our own prefix means every client needs
telling about us, which is the thing standards exist to avoid.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Body, Depends, Header, Query, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from acmis.core.abac import authorize
from acmis.core.audit import AuditCategory, emit
from acmis.core.deps import AnyContext, StaffContext, tenant_db, tenant_of
from acmis.core.errors import Forbidden, NotFound, Unauthenticated
from acmis.core.schemas import Schema
from acmis.modules.interop import lti as lti_service
from acmis.modules.interop import oneroster as or_service
from acmis.modules.interop import qti as qti_service
from acmis.modules.interop.models import (
    ContentPackage,
    LtiLineItem,
    LtiResourceLink,
    LtiTool,
)
from acmis.modules.learning import service as learning_service
from acmis.routers._common import get_or_404

log = structlog.get_logger(__name__)

router = APIRouter(tags=["interop"])


def _base_url(request: Request) -> str:
    return str(request.base_url).rstrip("/")


# ---------------------------------------------------------------------------
# LTI 1.3 — platform
# ---------------------------------------------------------------------------

lti = APIRouter(prefix="/lti", tags=["interop"])


class LtiToolIn(Schema):
    name: Annotated[str, Field(max_length=200)]
    issuer: Annotated[str, Field(max_length=300)]
    oidc_login_url: Annotated[str, Field(max_length=500, pattern=r"^https://")]
    target_link_uri: Annotated[str, Field(max_length=500, pattern=r"^https://")]
    jwks_url: Annotated[str | None, Field(max_length=500, pattern=r"^https://")] = None
    allow_deep_linking: bool = False
    allow_grade_services: bool = False
    allow_names_and_roles: bool = False
    disclose_emails: bool = False
    custom_parameters: dict[str, Any] = Field(default_factory=dict)
    unit_ids: list[uuid.UUID] = Field(default_factory=list)


class LtiToolOut(Schema):
    id: uuid.UUID
    name: str
    client_id: str
    issuer: str
    oidc_login_url: str
    target_link_uri: str
    jwks_url: str | None
    deployment_id: str
    allow_deep_linking: bool
    allow_grade_services: bool
    allow_names_and_roles: bool
    disclose_emails: bool
    status: str
    launch_count: int
    last_launch_at: datetime | None


@lti.post("/tools", response_model=LtiToolOut, status_code=status.HTTP_201_CREATED)
def register_tool(payload: LtiToolIn, ctx: StaffContext) -> LtiToolOut:
    """Register an external tool.

    Arrives `pending`. Each Advantage service is granted individually, and the
    grants are the whole point: a content tool needs Deep Linking and nothing
    else, and giving it grade-write access because it was easier is how a
    courseware vendor ends up able to change marks. Names and Roles discloses
    a class list to a third party, so it is off by default and gated again on
    whether email addresses go with it.
    """
    import secrets

    authorize(
        engine=ctx.engine,
        action="lti_tool:create",
        resource_type="api_client",
        resource={
            "id": None,
            "owner_id": str(ctx.principal.id),
            "status": "pending",
            "environment": "live",
        },
        category=AuditCategory.INTEGRATION,
    )
    tool = LtiTool(
        client_id=f"acmis-lti-{secrets.token_hex(10)}",
        deployment_id=secrets.token_hex(8),
        status="pending",
        created_by_id=ctx.principal.id,
        **payload.model_dump(),
    )
    ctx.db.add(tool)
    ctx.db.flush()
    emit(
        "lti_tool:create",
        AuditCategory.INTEGRATION,
        resource_type="api_client",
        resource_id=tool.id,
        resource_label=f"{tool.name} ({tool.client_id})",
        summary=(
            f"LTI tool registered; deep_linking={payload.allow_deep_linking}, "
            f"grades={payload.allow_grade_services}, nrps={payload.allow_names_and_roles}"
        ),
        severity="notice",
    )
    return LtiToolOut.model_validate(tool)


@lti.get("/{tenant_slug}/.well-known/jwks.json")
def platform_jwks(
    tenant_slug: str, request: Request, db: Session = Depends(tenant_db)
) -> dict[str, Any]:
    """This platform's public keys.

    Unauthenticated by necessity — a tool fetches it to verify our signatures,
    before any trust exists between us. Public keys are public; that is what
    makes them public keys.
    """
    tenant_of(request)
    return lti_service.jwks(db)


@lti.get("/{tenant_slug}/.well-known/openid-configuration")
def platform_configuration(
    tenant_slug: str, request: Request, db: Session = Depends(tenant_db)
) -> dict[str, Any]:
    """Platform discovery, so a tool can be configured by URL alone.

    Manual configuration of an LTI registration is six URLs and a client id
    typed into a vendor's form, and one typo produces a launch that fails with
    no useful message. Discovery removes most of that.
    """
    tenant = tenant_of(request)
    base = _base_url(request)
    issuer = lti_service.platform_issuer(tenant.slug, base)
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{base}/lti/{tenant.slug}/authorize",
        "token_endpoint": f"{base}/lti/{tenant.slug}/token",
        "jwks_uri": f"{base}/lti/{tenant.slug}/.well-known/jwks.json",
        "registration_endpoint": f"{base}/lti/{tenant.slug}/register",
        "scopes_supported": [
            lti_service.SCOPE_LINEITEM,
            lti_service.SCOPE_LINEITEM_READONLY,
            lti_service.SCOPE_RESULT_READONLY,
            lti_service.SCOPE_SCORE,
            lti_service.SCOPE_NRPS,
        ],
        "response_types_supported": ["id_token"],
        "subject_types_supported": ["public", "pairwise"],
        "id_token_signing_alg_values_supported": ["RS256"],
        "claims_supported": ["sub", "iss", "name", "given_name", "family_name", "email"],
        "https://purl.imsglobal.org/spec/lti-platform-configuration": {
            "product_family_code": "acmis",
            "version": "1.0",
            "messages_supported": [
                {"type": lti_service.MESSAGE_RESOURCE_LINK},
                {"type": lti_service.MESSAGE_DEEP_LINKING},
            ],
            "variables": ["ResourceLink.id", "Context.id", "User.id"],
        },
    }


class LaunchRequestOut(Schema):
    #: The tool's OIDC login endpoint, and the parameters to send it. The
    #: browser does the redirect; the API does not follow it, because the
    #: whole point of the flow is that the user's own browser carries it.
    oidc_login_url: str
    parameters: dict[str, str]


@lti.post("/resource-links/{link_id}/launch", response_model=LaunchRequestOut)
def begin_launch(link_id: uuid.UUID, ctx: AnyContext) -> LaunchRequestOut:
    """Step 1 of a launch: the parameters to post to the tool."""
    link = get_or_404(ctx, LtiResourceLink, link_id)
    tool = ctx.db.get(LtiTool, link.tool_id)
    if tool is None:
        raise NotFound()

    authorize(
        engine=ctx.engine,
        action="lti_resource_link:launch",
        resource_type="course_space",
        resource={
            "id": str(link.space_id) if link.space_id else None,
            "course_offering_id": str(link.course_offering_id),
            "is_registered": True,
            "is_published": True,
        },
        category=AuditCategory.INTEGRATION,
    )

    parameters = lti_service.begin_launch(
        ctx.db,
        tool=tool,
        resource_link=link,
        account_id=ctx.principal.id,
    )
    base = _base_url(ctx.request)
    parameters["iss"] = lti_service.platform_issuer(ctx.tenant.slug, base)

    tool.launch_count += 1
    tool.last_launch_at = datetime.now(tz=None).astimezone()
    ctx.db.flush()

    emit(
        "lti_resource_link:launch",
        AuditCategory.INTEGRATION,
        resource_type="api_client",
        resource_id=tool.id,
        resource_label=tool.name,
        summary=f"Launch initiated for '{link.title}'",
    )
    return LaunchRequestOut(oidc_login_url=tool.oidc_login_url, parameters=parameters)


@lti.post("/{tenant_slug}/authorize", response_class=HTMLResponse)
def authorize_launch(
    tenant_slug: str,
    request: Request,
    db: Session = Depends(tenant_db),
    client_id: Annotated[str, Body()] = "",
    redirect_uri: Annotated[str, Body()] = "",
    nonce: Annotated[str, Body()] = "",
    state: Annotated[str, Body()] = "",
    login_hint: Annotated[str, Body()] = "",
    lti_message_hint: Annotated[str, Body()] = "",
) -> HTMLResponse:
    """Step 3: mint the `id_token` and auto-post it to the tool.

    Everything is validated before anything is signed: the client id must
    resolve to an active registration, the `redirect_uri` must be one the tool
    registered (an unvalidated redirect here is an open redirect that carries
    an authentication token), and the nonce must not have been used.

    An HTML auto-submitting form rather than a 302, because the response is a
    POST — which is what the specification requires and what every tool
    expects.
    """
    tenant = tenant_of(request)
    tool = db.execute(select(LtiTool).where(LtiTool.client_id == client_id)).scalar_one_or_none()
    if tool is None or tool.status != "active":
        raise Unauthenticated("Unknown or inactive tool registration.")
    if redirect_uri and not redirect_uri.startswith(tool.target_link_uri.rsplit("/", 1)[0]):
        # An unvalidated redirect_uri would make this an open redirect that
        # hands an authentication token to wherever the caller names.
        raise Forbidden("redirect_uri does not match this tool's registration.")

    lti_service.check_and_consume_nonce(db, nonce=nonce, client_id=client_id)

    base = _base_url(request)
    issuer = lti_service.platform_issuer(tenant.slug, base)
    account_id = uuid.UUID(login_hint) if login_hint else uuid.UUID(int=0)
    subject = lti_service.tool_subject(tool=tool, account_id=account_id, issuer=issuer)

    _hint, _, remainder = lti_message_hint.partition(":")
    message_type, _, link_id = remainder.partition(":")
    message_type = message_type or lti_service.MESSAGE_RESOURCE_LINK
    link = db.get(LtiResourceLink, uuid.UUID(link_id)) if link_id else None

    from acmis.modules.identity.models import UserAccount

    account = db.get(UserAccount, account_id)
    principal_like = type(
        "P",
        (),
        {
            "kind": account.kind if account else "staff",
            "permissions": frozenset(),
        },
    )()
    roles = lti_service.lti_roles_for(principal=principal_like, is_instructor=False)

    claims = lti_service.build_id_token_claims(
        tool=tool,
        issuer=issuer,
        subject=subject,
        nonce=nonce,
        message_type=message_type,
        resource_link=link,
        context={
            "id": str(link.course_offering_id) if link else str(tenant.id),
            "label": tenant.slug,
            "title": tenant.name,
            "type": ["http://purl.imsglobal.org/vocab/lis/v2/course#CourseOffering"],
            "platform_name": tenant.name,
        },
        roles=roles,
        user={
            "name": account.display_name if account else None,
            "email": account.email if account and tool.disclose_emails else None,
        },
        services_base=base,
        deep_linking_return_url=f"{base}/lti/{tenant.slug}/deep-linking/return",
    )

    key = lti_service.ensure_platform_key(db, tenant_slug=tenant.slug)
    from jose import jwt as jose_jwt

    id_token = jose_jwt.encode(
        claims, key.private_key_ref, algorithm=key.algorithm, headers={"kid": key.kid}
    )

    emit(
        "lti:authorize",
        AuditCategory.INTEGRATION,
        resource_type="api_client",
        resource_id=tool.id,
        resource_label=tool.name,
        summary=f"{message_type} minted for {tool.name}",
    )

    # `id_token` and `state` are the only fields, per the specification.
    return HTMLResponse(
        f"""<!doctype html><html><body onload="document.forms[0].submit()">
<form method="post" action="{redirect_uri}">
  <input type="hidden" name="id_token" value="{id_token}"/>
  <input type="hidden" name="state" value="{state}"/>
  <noscript><button type="submit">Continue to {tool.name}</button></noscript>
</form></body></html>"""
    )


class ScoreIn(Schema):
    """The AGS score payload. Field names are the specification's, in camelCase."""

    userId: str  # noqa: N815 - the wire format is not ours to rename
    scoreGiven: float | None = None  # noqa: N815
    scoreMaximum: float | None = None  # noqa: N815
    activityProgress: str  # noqa: N815
    gradingProgress: str  # noqa: N815
    timestamp: str
    comment: str | None = None


@lti.post(
    "/{client_id}/lineitems/{line_item_id}/scores",
    status_code=status.HTTP_201_CREATED,
)
def post_score(
    client_id: str,
    line_item_id: uuid.UUID,
    payload: ScoreIn,
    request: Request,
    db: Session = Depends(tenant_db),
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Receive a score from a tool.

    The scores accumulate here; they do not reach a mark sheet until a member
    of staff pushes them, and then only onto a draft one. A tool reporting a
    grade does not get to bypass moderation and Senate because it arrived over
    HTTP.
    """
    tenant_of(request)
    tool = db.execute(select(LtiTool).where(LtiTool.client_id == client_id)).scalar_one_or_none()
    if tool is None or tool.status != "active":
        raise Unauthenticated("Unknown tool.")
    if not authorization:
        raise Unauthenticated("An AGS access token is required.")

    line_item = db.get(LtiLineItem, line_item_id)
    if line_item is None or line_item.tool_id != tool.id:
        raise NotFound()

    from acmis.modules.interop.models import ExternalIdentifier

    mapping = db.execute(
        select(ExternalIdentifier).where(
            ExternalIdentifier.system == "oneroster",
            ExternalIdentifier.external_id == payload.userId,
        )
    ).scalar_one_or_none()
    student_id = mapping.resource_id if mapping else _as_uuid(payload.userId)
    if student_id is None:
        raise NotFound("That user identifier does not resolve to a student.")

    lti_service.record_score(
        db,
        tool=tool,
        line_item=line_item,
        student_id=student_id,
        payload=payload.model_dump(),
    )
    return {"resultUrl": f"lineitems/{line_item_id}/results/{student_id}"}


def _as_uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError):
        return None


@lti.get("/{client_id}/lineitems/{line_item_id}/results")
def get_results(
    client_id: str,
    line_item_id: uuid.UUID,
    request: Request,
    db: Session = Depends(tenant_db),
) -> JSONResponse:
    tenant_of(request)
    tool = db.execute(select(LtiTool).where(LtiTool.client_id == client_id)).scalar_one_or_none()
    if tool is None or not tool.allow_grade_services:
        raise Forbidden()
    line_item = db.get(LtiLineItem, line_item_id)
    if line_item is None or line_item.tool_id != tool.id:
        raise NotFound()
    return JSONResponse(
        content=lti_service.current_results(db, line_item=line_item),
        media_type=lti_service.MEDIA_RESULT_CONTAINER,
    )


@lti.post("/line-items/{line_item_id}/push-marks", response_model=dict)
def push_line_item(line_item_id: uuid.UUID, ctx: StaffContext) -> dict[str, Any]:
    """Write a tool's reported grades into the mark sheet."""
    from acmis.modules.assessment.models import MarkSheet

    line_item = get_or_404(ctx, LtiLineItem, line_item_id)
    sheet = ctx.db.execute(
        select(MarkSheet).where(MarkSheet.course_offering_id == line_item.course_offering_id)
    ).scalar_one_or_none()
    authorize(
        engine=ctx.engine,
        action="online_assessment:push_marks",
        resource_type="online_assessment",
        resource={
            "id": str(line_item.id),
            "course_offering_id": str(line_item.course_offering_id),
            "status": "released",
            "department_ids": [],
            "faculty_ids": [],
        },
        extra_attributes={"mark_sheet_status": sheet.status if sheet else None},
        category=AuditCategory.ASSESSMENT,
    )
    return lti_service.push_line_item_to_mark_sheet(
        ctx.db, line_item=line_item, actor_id=ctx.principal.id
    )


# ---------------------------------------------------------------------------
# OneRoster 1.2
# ---------------------------------------------------------------------------

oneroster = APIRouter(prefix=or_service.BASE_PATH, tags=["interop"])


def _paged(items: list[dict[str, Any]], collection: str, limit: int, offset: int) -> JSONResponse:
    page, headers = or_service.apply_paging(items, limit=limit, offset=offset)
    return JSONResponse(content=or_service.envelope(collection, page), headers=headers)


@oneroster.get("/orgs")
def or_orgs(
    ctx: AnyContext,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> JSONResponse:
    """Orgs: the institution and its faculties and departments."""
    from acmis.modules.shared.models import AcademicUnit

    authorize(
        engine=ctx.engine,
        action="oneroster:read",
        resource_type="institution",
        resource={"id": str(ctx.tenant.id), "slug": ctx.tenant.slug, "status": "active"},
        category=AuditCategory.INTEGRATION,
        audit_reads=True,
    )
    base = _base_url(ctx.request)
    items = [or_service.org_payload(ctx.db, tenant=ctx.tenant, base_url=base)]
    units = (
        ctx.db.execute(select(AcademicUnit).where(AcademicUnit.deleted_at.is_(None)))
        .scalars()
        .all()
    )
    items += [or_service.unit_payload(ctx.db, unit=u, base_url=base) for u in units]
    return _paged(items, "orgs", limit, offset)


@oneroster.get("/academicSessions")
def or_sessions(
    ctx: AnyContext,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> JSONResponse:
    from acmis.modules.shared.models import AcademicYear, Semester

    authorize(
        engine=ctx.engine,
        action="oneroster:read",
        resource_type="institution",
        resource={"id": str(ctx.tenant.id), "slug": ctx.tenant.slug, "status": "active"},
        category=AuditCategory.INTEGRATION,
    )
    base = _base_url(ctx.request)
    semesters = (
        ctx.db.execute(select(Semester).where(Semester.deleted_at.is_(None))).scalars().all()
    )
    items = []
    for semester in semesters:
        year = ctx.db.get(AcademicYear, semester.academic_year_id)
        items.append(
            or_service.academic_session_payload(ctx.db, semester=semester, year=year, base_url=base)
        )
    return _paged(items, "academicSessions", limit, offset)


@oneroster.get("/courses")
def or_courses(
    ctx: AnyContext,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> JSONResponse:
    from acmis.modules.curriculum.models import Programme

    authorize(
        engine=ctx.engine,
        action="oneroster:read",
        resource_type="programme",
        resource={"id": None, "status": "approved"},
        category=AuditCategory.INTEGRATION,
    )
    base = _base_url(ctx.request)
    rows = ctx.db.execute(select(Programme).where(Programme.deleted_at.is_(None))).scalars().all()
    items = [or_service.course_payload(ctx.db, programme=p, base_url=base) for p in rows]
    return _paged(items, "courses", limit, offset)


@oneroster.get("/classes")
def or_classes(
    ctx: AnyContext,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> JSONResponse:
    from acmis.modules.curriculum.models import CourseOffering

    authorize(
        engine=ctx.engine,
        action="oneroster:read",
        resource_type="course_offering",
        resource={"id": None, "status": "approved", "is_open": True},
        category=AuditCategory.INTEGRATION,
    )
    base = _base_url(ctx.request)
    rows = (
        ctx.db.execute(select(CourseOffering).where(CourseOffering.deleted_at.is_(None)))
        .scalars()
        .all()
    )
    items = [or_service.class_payload(ctx.db, offering=o, base_url=base) for o in rows]
    return _paged(items, "classes", limit, offset)


@oneroster.get("/enrollments")
def or_enrollments(
    ctx: AnyContext,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> JSONResponse:
    from acmis.modules.students.models import RegistrationCourse

    authorize(
        engine=ctx.engine,
        action="oneroster:read_enrollments",
        resource_type="registration",
        resource={"id": None, "status": "approved"},
        category=AuditCategory.INTEGRATION,
        audit_reads=True,
    )
    base = _base_url(ctx.request)
    rows = (
        ctx.db.execute(select(RegistrationCourse).where(RegistrationCourse.deleted_at.is_(None)))
        .scalars()
        .all()
    )
    items = [
        or_service.enrollment_payload(ctx.db, registration_course=r, base_url=base) for r in rows
    ]
    return _paged(items, "enrollments", limit, offset)


@oneroster.get("/users")
def or_users(
    ctx: AnyContext,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    role: str | None = None,
) -> JSONResponse:
    """Users: students and staff.

    Contact details are disclosed only if the calling client's registration
    says so. A rostering feed to a library system needs names and student
    numbers; it does not need phone numbers, and a standard that makes it easy
    to send everything is not a reason to.
    """
    from acmis.modules.people.models import Staff
    from acmis.modules.students.models import Student

    decision = authorize(
        engine=ctx.engine,
        action="oneroster:read_users",
        resource_type="student",
        resource={"id": None, "status": "active"},
        category=AuditCategory.INTEGRATION,
        audit_reads=True,
    )
    disclose = "email" not in decision.masked_fields
    base = _base_url(ctx.request)
    items: list[dict[str, Any]] = []

    if role in {None, "student"}:
        for student in ctx.db.execute(
            select(Student).where(Student.deleted_at.is_(None))
        ).scalars():
            items.append(
                or_service.student_user_payload(
                    ctx.db, student=student, base_url=base, disclose_contact=disclose
                )
            )
    if role in {None, "teacher"}:
        for staff in ctx.db.execute(select(Staff).where(Staff.deleted_at.is_(None))).scalars():
            items.append(
                or_service.staff_user_payload(
                    ctx.db, staff=staff, base_url=base, disclose_contact=disclose
                )
            )
    return _paged(items, "users", limit, offset)


@oneroster.get("/students")
def or_students(
    ctx: AnyContext,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> JSONResponse:
    return or_users(ctx=ctx, limit=limit, offset=offset, role="student")


@oneroster.get("/teachers")
def or_teachers(
    ctx: AnyContext,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> JSONResponse:
    return or_users(ctx=ctx, limit=limit, offset=offset, role="teacher")


# ---------------------------------------------------------------------------
# QTI
# ---------------------------------------------------------------------------

qti = APIRouter(prefix="/qti", tags=["interop"])


class QtiImportIn(Schema):
    question_bank_id: uuid.UUID
    #: `[{name, xml}]`. A whole package is unzipped by the client or by the
    #: upload endpoint; this takes the items.
    items: Annotated[list[dict[str, str]], Field(min_length=1, max_length=2000)]
    source_system: str | None = None


@qti.post("/import", response_model=dict)
def import_qti(payload: QtiImportIn, ctx: StaffContext) -> dict[str, Any]:
    """Import QTI 2.1 or 3.0 items into a question bank.

    Failures are named, not swallowed. A 400-question export with three
    unparseable items yields 397 questions and three reasons — an import that
    silently drops what it could not read is a migration nobody can trust.
    """
    from acmis.modules.learning.models import QuestionBank

    bank = get_or_404(ctx, QuestionBank, payload.question_bank_id)
    authorize(
        engine=ctx.engine,
        action="question:import",
        resource_type="question_bank",
        resource=bank,
        category=AuditCategory.ASSESSMENT,
    )

    report = qti_service.import_package(
        [(item.get("name", "item"), item.get("xml", "")) for item in payload.items]
    )

    created = 0
    for question in report.imported:
        try:
            from acmis.modules.learning import service as learning

            learning.create_question(
                ctx.db,
                bank=bank,
                payload={
                    "kind": question.kind,
                    "stem": question.stem,
                    "marks": question.marks,
                    "answer_key": question.answer_key,
                    "explanation": question.explanation,
                    "topic": question.topic,
                    "options": question.options,
                },
                actor_id=ctx.principal.id,
            )
            created += 1
        except Exception as exc:  # a rejected question is reported, not fatal
            report.failures.append(
                {"item": question.identifier or question.stem[:40], "reason": str(exc)}
            )

    package = ContentPackage(
        format="qti_3p0",
        title=f"QTI import into {bank.code}",
        source_system=payload.source_system,
        question_bank_id=bank.id,
        status="imported",
        items_found=len(payload.items),
        items_imported=created,
        failures=report.failures,
        imported_by_id=ctx.principal.id,
        imported_at=datetime.now(tz=None).astimezone(),
        created_by_id=ctx.principal.id,
    )
    ctx.db.add(package)
    ctx.db.flush()

    emit(
        "content_package:import",
        AuditCategory.ASSESSMENT,
        resource_type="question_bank",
        resource_id=bank.id,
        resource_label=bank.code,
        summary=f"QTI import: {created} of {len(payload.items)} item(s) imported",
        metadata={"failures": report.failures[:50]},
        severity="notice",
    )
    return {
        "package_id": str(package.id),
        "found": len(payload.items),
        "imported": created,
        "failed": len(report.failures),
        "failures": report.failures,
    }


@qti.get("/banks/{bank_id}/export")
def export_qti(bank_id: uuid.UUID, ctx: StaffContext) -> dict[str, Any]:
    """Export a bank as QTI 3.0 items.

    Round-tripping matters for the same reason importing does: an institution
    should be able to leave. A question bank that can only be read through our
    own API is a question bank held hostage.
    """
    from acmis.modules.learning.models import Question, QuestionBank

    bank = get_or_404(ctx, QuestionBank, bank_id)
    authorize(
        engine=ctx.engine,
        action="question:export",
        resource_type="question_bank",
        resource=bank,
        # Supplied here rather than in the descriptor: it is a query across the
        # assessment tables, not a column, and `interop.question-interchange`
        # refuses the export while it is true.
        extra_attributes={
            "has_open_assessment": learning_service.bank_has_open_paper(ctx.db, bank_id=bank.id)
        },
        category=AuditCategory.DATA_EXPORT,
        audit_reads=True,
    )
    rows = (
        ctx.db.execute(
            select(Question).where(
                Question.bank_id == bank.id,
                Question.deleted_at.is_(None),
                Question.is_active.is_(True),
            )
        )
        .scalars()
        .all()
    )
    return {
        "bank": {"code": bank.code, "name": bank.name},
        "format": "qti_3p0",
        "items": [
            {"identifier": f"acmis-{q.id}", "xml": qti_service.export_question(q)} for q in rows
        ],
    }


router.include_router(lti)
router.include_router(oneroster)
router.include_router(qti)
