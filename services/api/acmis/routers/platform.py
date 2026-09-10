"""Control-plane endpoints: tenant lifecycle, plans, impersonation.

These do not resolve a tenant from the host — they *are* the endpoints that
create and administer tenants. They run against the control-plane database and
are reachable only by a `platform` principal, which the baseline policy grants
nothing inside a tenant's academic data.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from acmis.core.abac.registry import registry
from acmis.core.deps import ControlSession, PageQuery, control_db, current_principal
from acmis.core.errors import Forbidden, NotFound
from acmis.core.pagination import keyset_page
from acmis.core.schemas import Page, Reason, Schema
from acmis.modules.tenancy import provisioning, service
from acmis.modules.tenancy.models import (
    ImpersonationSession,
    Plan,
    PlatformUser,
    Tenant,
)

router = APIRouter(prefix="/platform", tags=["platform"])


class PlatformLoginIn(Schema):
    email: EmailStr
    password: Annotated[str, Field(min_length=1, max_length=200)]


class PlatformTokenOut(Schema):
    access_token: str
    # The OAuth 2.0 response field, not a credential.
    token_type: str = "bearer"  # noqa: S105
    permissions: list[str]
    mfa_enrolled: bool


@router.post("/login", response_model=PlatformTokenOut)
def platform_login(
    payload: PlatformLoginIn, control: Session = Depends(control_db)
) -> PlatformTokenOut:
    user, token = service.authenticate_platform_user(
        control, email=payload.email, password=payload.password
    )
    return PlatformTokenOut(
        access_token=token,
        permissions=sorted(user.permissions or ()),
        mfa_enrolled=user.mfa_enrolled_at is not None,
    )


class TenantOut(Schema):
    id: uuid.UUID
    slug: str
    name: str
    short_name: str
    status: str
    database_name: str
    region: str
    country_code: str
    city: str | None
    currency: str
    locale: str
    timezone: str
    regulator_code: str | None
    enabled_features: list[str]
    policy_revision: int
    schema_revision: str | None
    schema_migrated_at: datetime | None
    onboarded_at: datetime | None
    suspended_at: datetime | None
    suspension_reason: str | None


def _require_platform(principal: Any = Depends(current_principal)) -> Any:
    if principal.kind != "platform":
        raise Forbidden("This endpoint is for platform administrators.")
    return principal


PlatformPrincipal = Annotated[Any, Depends(_require_platform)]


@router.get("/tenants", response_model=Page[TenantOut])
def list_tenants(
    principal: PlatformPrincipal,
    control: ControlSession,
    page: PageQuery,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
) -> Page[TenantOut]:
    if "platform:admin" not in principal.permissions and (
        "platform:support" not in principal.permissions
    ):
        raise Forbidden()
    stmt = select(Tenant)
    if status_filter:
        stmt = stmt.where(Tenant.status == status_filter)
    found = keyset_page(control, stmt, page=page, key=Tenant.slug, ident=Tenant.id)
    return Page.of(
        [TenantOut.model_validate(r) for r in found.rows],
        limit=page.limit,
        next_cursor=found.next_cursor,
        total=found.total,
    )


class ProvisionIn(Schema):
    name: Annotated[str, Field(max_length=200)]
    short_name: Annotated[str, Field(max_length=20)]
    slug: Annotated[str | None, Field(max_length=40)] = None
    country_code: str = "UG"
    city: str | None = None
    currency: str = "UGX"
    locale: str = "en-UG"
    timezone: str = "Africa/Kampala"
    regulator_code: str | None = None
    plan_code: str | None = None
    region: str = "eu-west-1"
    enabled_features: list[str] = Field(default_factory=list)
    primary_hostname: str | None = None
    seed_reference_data: bool = True


@router.post("/tenants", response_model=TenantOut, status_code=status.HTTP_201_CREATED)
def provision_tenant(payload: ProvisionIn, principal: PlatformPrincipal) -> TenantOut:
    """Onboard a university: create its database, migrate it, seed it.

    Synchronous, which is a deliberate choice for an operation performed a few
    times a year: the caller finds out whether it worked. A tenant that fails
    part-way is left visible as `provisioning`/`failed` rather than
    half-created and forgotten.
    """
    if "platform:admin" not in principal.permissions:
        raise Forbidden()
    tenant = provisioning.provision(
        provisioning.ProvisionRequest(**payload.model_dump()), actor_id=principal.id
    )
    return TenantOut.model_validate(tenant)


class TenantStatusIn(Reason):
    status: Annotated[str, Field(pattern="^(active|read_only|suspended|archived)$")]


@router.post("/tenants/{tenant_id}/status", response_model=TenantOut)
def set_tenant_status(
    tenant_id: uuid.UUID,
    payload: TenantStatusIn,
    principal: PlatformPrincipal,
    control: ControlSession,
) -> TenantOut:
    """Change a tenant's standing. Takes effect on the next request.

    `read_only` rather than `suspended` is the right lever for a payment
    dispute: locking a registry out mid-semester punishes students for a
    disagreement between two finance departments.
    """
    if "platform:admin" not in principal.permissions:
        raise Forbidden()
    tenant = control.get(Tenant, tenant_id)
    if tenant is None:
        raise NotFound()
    updated = service.set_tenant_status(
        control, tenant=tenant, status=payload.status, reason=payload.reason
    )
    return TenantOut.model_validate(updated)


@router.get("/tenants/migration-status", response_model=list[dict[str, Any]])
def migration_status(principal: PlatformPrincipal) -> list[dict[str, Any]]:
    """Which tenants are on which schema revision.

    The fan-out's dashboard. Database-per-tenant means a migration is 200
    migrations, and the only way that is operable is being able to see which
    ones lag without connecting to all of them.
    """
    if "platform:admin" not in principal.permissions:
        raise Forbidden()
    return provisioning.migration_status()


class MigrateAllIn(Schema):
    revision: str = "head"
    concurrency: Annotated[int, Field(ge=1, le=16)] = 4
    only: list[str] = Field(default_factory=list)


@router.post("/tenants/migrate", response_model=dict)
def migrate_all(
    principal: PlatformPrincipal, payload: MigrateAllIn | None = None
) -> dict[str, Any]:
    """Fan a migration across every active tenant.

    Bounded concurrency, and failures are collected rather than raised: one
    university with a lock held by a long-running report must not stop the
    other 199. The response names which to retry.
    """
    body = payload or MigrateAllIn()
    if "platform:admin" not in principal.permissions:
        raise Forbidden()
    return provisioning.migrate_all(
        revision=body.revision,
        concurrency=body.concurrency,
        only=body.only or None,
    )


class PlanOut(Schema):
    id: uuid.UUID
    code: str
    name: str
    description: str | None
    included_modules: list[str]
    price_per_student_minor: int
    currency: str
    max_students: int | None
    support_tier: str
    is_active: bool


@router.get("/plans", response_model=list[PlanOut])
def list_plans(principal: PlatformPrincipal, control: ControlSession) -> list[PlanOut]:
    rows = control.execute(select(Plan).order_by(Plan.price_per_student_minor)).scalars().all()
    return [PlanOut.model_validate(r) for r in rows]


class ImpersonationIn(Schema):
    tenant_id: uuid.UUID
    reason: Annotated[str, Field(min_length=15, max_length=500)]
    ticket_reference: str | None = None
    target_user_id: uuid.UUID | None = None


class ImpersonationOut(Schema):
    id: uuid.UUID
    tenant_id: uuid.UUID
    access_token: str
    expires_at: datetime
    reason: str
    #: Restated in the response because it is the thing support staff most
    #: need to know before they start clicking.
    constraints: str = (
        "This session is read-only inside the institution and cannot open "
        "special-category records. Every action is recorded in the institution's own "
        "audit trail."
    )


@router.post("/impersonation", response_model=ImpersonationOut, status_code=status.HTTP_201_CREATED)
def start_impersonation(
    payload: ImpersonationIn, principal: PlatformPrincipal, control: ControlSession
) -> ImpersonationOut:
    """Open a read-only support session inside a university.

    Read-only is enforced by `baseline.impersonation-limits`, which applies to
    every endpoint including ones written after this one. What is enforced here
    is the front door: a stated reason, a 30-minute expiry, and the
    institution's own approval where its contract requires it.
    """
    if "platform:support" not in principal.permissions and (
        "platform:admin" not in principal.permissions
    ):
        raise Forbidden()

    tenant = control.get(Tenant, payload.tenant_id)
    if tenant is None:
        raise NotFound()
    user = control.get(PlatformUser, principal.id)
    if user is None:
        raise NotFound()

    require_approval = bool((tenant.runtime_settings or {}).get("require_support_approval", False))
    session_row, token = service.start_impersonation(
        control,
        platform_user=user,
        tenant=tenant,
        reason=payload.reason,
        ticket_reference=payload.ticket_reference,
        target_user_id=payload.target_user_id,
        require_tenant_approval=require_approval,
        approved_by_id=None,
    )
    return ImpersonationOut(
        id=session_row.id,
        tenant_id=tenant.id,
        access_token=token,
        expires_at=session_row.expires_at,
        reason=session_row.reason,
    )


@router.post("/impersonation/{session_id}/end", status_code=status.HTTP_204_NO_CONTENT)
def end_impersonation(
    session_id: uuid.UUID, principal: PlatformPrincipal, control: ControlSession
) -> None:
    row = control.get(ImpersonationSession, session_id)
    if row is None:
        raise NotFound()
    service.end_impersonation(control, session_row=row)


@router.get("/fleet", response_model=list[dict[str, Any]])
def fleet_overview(principal: PlatformPrincipal, control: ControlSession) -> list[dict[str, Any]]:
    if "platform:admin" not in principal.permissions:
        raise Forbidden()
    return service.tenant_health(control)


@router.post("/policies/reload", response_model=dict)
def reload_policies(principal: PlatformPrincipal) -> dict[str, Any]:
    """Reload the builtin policy bundle from disk without a restart.

    Used after a deployment that ships policy changes. A bundle that fails to
    load leaves the previous one in place — a typo must not take the fleet
    offline.
    """
    if "platform:admin" not in principal.permissions:
        raise Forbidden()
    registry.load_builtin()
    engine = registry.default_engine()
    return {
        "policies": len(engine.policies),
        "rules": sum(len(p.rules) for p in engine.policies),
        "bundle_version": engine.version,
        "lint": engine.lint() or "clean",
    }
