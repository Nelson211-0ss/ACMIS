"""FastAPI dependencies — the wiring every endpoint declares.

An endpoint's signature is meant to read as its security contract:

    @router.post("/mark-sheets/{sheet_id}/submit")
    def submit(sheet_id: UUID, ctx: StaffContext) -> MarkSheetOut: ...

`StaffContext` carries the tenant session, the authenticated principal, the
policy engine and the audit writer, all resolved and consistent with each
other. The alternative — four separate dependencies per endpoint — is the same
thing with more places to forget one.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Annotated

import structlog
from fastapi import Depends, Header, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from acmis.core.abac.engine import PolicyEngine
from acmis.core.abac.registry import registry
from acmis.core.audit import AuditWriter, attach_writer, detach_writer
from acmis.core.context import (
    Principal,
    RequestContext,
    TenantContext,
    replace_context,
)
from acmis.core.db import ControlSessionLocal, tenant_engine
from acmis.core.errors import Forbidden, TenantNotResolved, Unauthenticated
from acmis.core.schemas import PageParams
from acmis.core.security import read_token

log = structlog.get_logger(__name__)

bearer = HTTPBearer(auto_error=False)


def request_context(request: Request) -> RequestContext:
    ctx: RequestContext | None = getattr(request.state, "acmis_context", None)
    if ctx is None:  # pragma: no cover - middleware not installed
        raise RuntimeError("RequestContextMiddleware is not installed")
    return ctx


def tenant_of(request: Request) -> TenantContext:
    ctx = request_context(request)
    if ctx.tenant is None:
        raise TenantNotResolved()
    return ctx.tenant


def control_db() -> Iterator[Session]:
    session = ControlSessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def tenant_db(request: Request) -> Iterator[Session]:
    """A session bound to *this* university's database.

    Every read and write an endpoint performs goes through here. There is no
    ambient "current database" to get wrong: the connection is chosen from the
    resolved tenant, and a tenant that failed to resolve produces no session at
    all rather than a session pointed at somewhere plausible.
    """
    tenant = tenant_of(request)
    engine = tenant_engine(key=tenant.slug, dsn=tenant.dsn)
    session = Session(bind=engine, autoflush=False, expire_on_commit=False)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def policy_engine(request: Request) -> PolicyEngine:
    """The engine for this tenant: builtin bundle plus that tenant's overlay.

    The overlay is only re-read when the tenant's `policy_revision` moves, so
    the common path is a dict lookup on an already-compiled bundle. A revision
    bump — someone edited a policy — costs one query and one compile, once, and
    then every subsequent request is back on the fast path.
    """
    ctx = request_context(request)
    if ctx.tenant is None:
        return registry.default_engine()

    revision = int(getattr(request.state, "acmis_policy_revision", 0))
    cached = registry.engine_for(ctx.tenant.id, overlay_revision=revision)
    if cached is not registry.default_engine():
        return cached

    return registry.engine_for(
        ctx.tenant.id,
        overlay_rows=_load_overlay_rows(ctx.tenant),
        overlay_revision=revision,
        tenant_slug=ctx.tenant.slug,
    )


def _load_overlay_rows(tenant: TenantContext) -> list[dict[str, object]]:
    """Read a tenant's policy overlay from its own database.

    Its own database, not the control plane: an institution's authorization
    rules are its data, and they travel with the dump it is handed on exit.
    """
    from acmis.modules.governance.models import PolicyOverlay

    engine = tenant_engine(key=tenant.slug, dsn=tenant.dsn)
    with Session(bind=engine) as session:
        rows = session.execute(
            select(PolicyOverlay).where(
                PolicyOverlay.deleted_at.is_(None), PolicyOverlay.enabled.is_(True)
            )
        ).scalars()
        return [dict(row.document) for row in rows]


def _principal_from_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None,
    control: Session,
) -> Principal:
    if credentials is None:
        raise Unauthenticated()

    claims = read_token(credentials.credentials, expect="access")
    subject_id = uuid.UUID(str(claims["sub"]))
    kind = str(claims.get("knd", "staff"))

    if kind == "platform":
        from acmis.modules.tenancy.service import load_platform_principal

        return load_platform_principal(control, subject_id, claims)

    tenant = tenant_of(request)
    from acmis.modules.identity.service import load_principal

    engine = tenant_engine(key=tenant.slug, dsn=tenant.dsn)
    with Session(bind=engine) as session:
        return load_principal(session, subject_id=subject_id, claims=claims, tenant_id=tenant.id)


def current_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)] = None,
    control: Session = Depends(control_db),
    api_key: Annotated[str | None, Header(alias="x-acmis-api-key")] = None,
) -> Principal:
    """Authenticate, and swap the resolved principal into the request context.

    Two credential shapes: a bearer access token for people, and an API key for
    machine callers from the developer portal. A request presenting both is
    refused — which credential's limits apply is not something to resolve by
    precedence, and an integration that sends both is misconfigured in a way
    worth surfacing loudly.
    """
    if api_key and credentials:
        raise Unauthenticated("Send either a bearer token or an API key, not both.")

    if api_key:
        from acmis.modules.developers.service import principal_for_api_key

        tenant = tenant_of(request)
        engine = tenant_engine(key=tenant.slug, dsn=tenant.dsn)
        with Session(bind=engine) as session:
            principal = principal_for_api_key(session, api_key=api_key, tenant_id=tenant.id)
    else:
        principal = _principal_from_token(request, credentials, control)

    ctx = request_context(request)
    updated = RequestContext(
        request_id=ctx.request_id,
        principal=principal,
        tenant=ctx.tenant,
        ip_address=ctx.ip_address,
        user_agent=ctx.user_agent,
        method=ctx.method,
        path=ctx.path,
        module=ctx.module,
    )
    request.state.acmis_context = updated
    # `replace_context`, not `set_context`: this dependency may be running in
    # a threadpool worker with a *copy* of the request's context, so installing
    # a new ContextVar value here would be invisible to the endpoint. Mutating
    # the shared holder is what every copy sees. See `_Holder` in core.context.
    replace_context(updated)
    return principal


def audit_writer(request: Request, session: Session = Depends(tenant_db)) -> Iterator[AuditWriter]:
    """The writer endpoints emit into, flushed in the endpoint's transaction.

    Flushed *before* the session's own commit in `tenant_db`, so the audit rows
    and the change they describe are one atomic unit. If the flush fails the
    request fails; a committed change with no audit line is not an outcome this
    system is allowed to produce.
    """
    ctx = request_context(request)
    writer = AuditWriter(session, ctx)
    attach_writer(ctx, writer)
    try:
        yield writer
    except Exception:
        # The request failed, so this session is rolling back and anything
        # flushed into it goes with it. A denial's audit record is precisely
        # what must survive that, so it is committed on its own connection.
        tenant = ctx.tenant
        if tenant is not None and writer.pending:
            writer.flush_out_of_band(dsn=tenant.dsn, tenant_key=tenant.slug)
        raise
    else:
        # Same transaction as the change it describes, on the success path —
        # see the note in `AuditWriter`. `tenant_db` commits after this.
        writer.flush()
    finally:
        detach_writer(ctx)


def page_params(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    with_total: Annotated[bool, Query()] = False,
) -> PageParams:
    """Pagination, as three explicit query parameters.

    A dependency rather than `Annotated[PageParams, Query()]`. The model form
    reads more nicely and does not work here: with a default value in the
    signature FastAPI binds the whole model as a *single* scalar query
    parameter named after the argument, so `?limit=2&with_total=true` was
    silently ignored on every list endpoint in the API and every caller got
    the defaults. Nothing errored — the page simply came back the wrong size,
    which is the sort of bug that survives a long time.

    Declaring the three explicitly also puts them in the OpenAPI document as
    three named parameters, which is what the generated client needs.
    """
    return PageParams(limit=limit, cursor=cursor, with_total=with_total)


#: What every list endpoint declares.
PageQuery = Annotated[PageParams, Depends(page_params)]


@dataclass(slots=True)
class Ctx:
    """Everything an endpoint needs, resolved consistently."""

    request: Request
    db: Session
    principal: Principal
    tenant: TenantContext
    engine: PolicyEngine
    audit: AuditWriter

    @property
    def context(self) -> RequestContext:
        return request_context(self.request)

    @property
    def student_id(self) -> uuid.UUID:
        """This actor's own student record.

        `StudentContext` narrows the principal's *kind*, not its links — a
        unified account can be staff-only, and an account whose student record
        was never attached would otherwise flow a `None` into a query and
        silently match nothing. Failing here says what is actually wrong.
        """
        if self.principal.student_id is None:
            raise Forbidden(
                "This account is not linked to a student record. Ask the registry to link it."
            )
        return self.principal.student_id

    @property
    def staff_id(self) -> uuid.UUID:
        """This actor's own staff record. Same reasoning as `student_id`."""
        if self.principal.staff_id is None:
            raise Forbidden(
                "This account is not linked to a staff record. Ask your system "
                "administrator to link it."
            )
        return self.principal.staff_id

    @property
    def applicant_id(self) -> uuid.UUID:
        """This actor's own applicant record. Same reasoning as `student_id`."""
        if self.principal.applicant_id is None:
            raise Forbidden("This account is not linked to an applicant record.")
        return self.principal.applicant_id


def build_ctx(
    request: Request,
    db: Session = Depends(tenant_db),
    principal: Principal = Depends(current_principal),
    engine: PolicyEngine = Depends(policy_engine),
    audit: AuditWriter = Depends(audit_writer),
) -> Ctx:
    return Ctx(
        request=request,
        db=db,
        principal=principal,
        tenant=tenant_of(request),
        engine=engine,
        audit=audit,
    )


AuthContext = Annotated[Ctx, Depends(build_ctx)]


def _require_kind(*kinds: str) -> Callable[[Ctx], Ctx]:
    def dependency(ctx: AuthContext) -> Ctx:
        if ctx.principal.kind not in kinds:
            # A 403 rather than a 404: the route exists, this actor is the
            # wrong sort of actor for it. Which is not sensitive — a student
            # learning that a staff endpoint exists learns nothing.
            raise Forbidden("This endpoint is not available to your account type.")
        return ctx

    return dependency


#: Narrowed contexts. A route that declares `StaffContext` cannot be reached by
#: a student token even if the policy bundle would have permitted the action —
#: two independent checks, which is what you want on the endpoints that matter.
StaffContext = Annotated[Ctx, Depends(_require_kind("staff", "platform"))]
StudentContext = Annotated[Ctx, Depends(_require_kind("student"))]
ApplicantContext = Annotated[Ctx, Depends(_require_kind("applicant"))]
ServiceContext = Annotated[Ctx, Depends(_require_kind("service"))]
AnyContext = AuthContext

TenantSession = Annotated[Session, Depends(tenant_db)]
ControlSession = Annotated[Session, Depends(control_db)]
PolicyEngineDep = Annotated[PolicyEngine, Depends(policy_engine)]
