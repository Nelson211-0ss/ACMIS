"""Control-plane operations: platform sign-in, tenant lifecycle, impersonation."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from acmis.core import tenant_resolver
from acmis.core.audit import AuditCategory, redact
from acmis.core.context import Principal, current_context
from acmis.core.errors import Forbidden, RuleViolation, Unauthenticated, ValidationFailed
from acmis.core.models import utcnow
from acmis.core.security import issue_token, verify_password
from acmis.modules.tenancy.models import (
    ImpersonationSession,
    PlatformAuditEvent,
    PlatformUser,
    Tenant,
    TenantStatus,
)

log = structlog.get_logger(__name__)


def load_platform_principal(
    control: Session, subject_id: uuid.UUID, claims: dict[str, Any]
) -> Principal:
    user = control.get(PlatformUser, subject_id)
    if user is None or user.status != "active":
        raise Unauthenticated("This account is not active.")
    return Principal(
        id=user.id,
        kind="platform",
        display_name=user.full_name,
        email=user.email,
        roles=frozenset({"platform"}),
        permissions=frozenset(user.permissions or ()),
        mfa_satisfied=bool(claims.get("mfa")) and user.mfa_enrolled_at is not None,
        extra={"status": user.status},
    )


def authenticate_platform_user(
    control: Session, *, email: str, password: str
) -> tuple[PlatformUser, str]:
    user = control.execute(
        select(PlatformUser).where(PlatformUser.email == email.strip().lower())
    ).scalar_one_or_none()
    generic = Unauthenticated("That email or password is not correct.")

    if user is None:
        raise generic
    now = utcnow()
    if user.locked_until and user.locked_until > now:
        raise generic
    if not verify_password(password, user.password_hash):
        user.failed_logins += 1
        if user.failed_logins >= 5:
            user.locked_until = now + timedelta(minutes=15)
        raise generic
    if user.status != "active":
        raise Forbidden("This account is not active.")

    user.failed_logins = 0
    user.locked_until = None
    user.last_login_at = now
    token = issue_token(
        subject_id=user.id,
        kind="access",
        claims={"knd": "platform", "mfa": user.mfa_enrolled_at is not None},
    )
    record_platform_event(
        control,
        action="platform:login",
        resource_type="platform_user",
        resource_id=str(user.id),
        summary=f"{user.email} signed in to the control plane",
    )
    return user, token


def record_platform_event(
    control: Session,
    *,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    summary: str | None = None,
    tenant_id: uuid.UUID | None = None,
    metadata: dict[str, Any] | None = None,
    outcome: str = "success",
) -> None:
    """Write to the platform's own trail.

    Separate from a tenant's `audit_event` on purpose. Handing a university a
    dump of its own database on exit must not hand it the platform's
    operational history — including which other institutions exist.
    """
    ctx = current_context()
    control.add(
        PlatformAuditEvent(
            occurred_at=utcnow(),
            request_id=ctx.request_id if ctx else None,
            actor_id=ctx.principal.id if ctx else None,
            actor_label=ctx.principal.display_name if ctx else None,
            tenant_id=tenant_id or (ctx.tenant.id if ctx and ctx.tenant else None),
            action=action,
            outcome=outcome,
            resource_type=resource_type,
            resource_id=resource_id,
            summary=summary,
            event_metadata=redact(metadata),
            ip_address=ctx.ip_address if ctx else None,
        )
    )


def set_tenant_status(
    control: Session, *, tenant: Tenant, status: str, reason: str | None = None
) -> Tenant:
    """Change a tenant's standing, and make it bite immediately.

    Two things beyond the column write. The resolver cache is invalidated, so a
    suspension takes effect on the next request rather than up to 30 seconds
    later. And a suspension records its reason, because "why can 12,000
    students not sign in" needs an answer at the moment it is asked.
    """
    if status not in set(TenantStatus):
        raise ValidationFailed(f"'{status}' is not a valid tenant status.")
    if status == TenantStatus.SUSPENDED and not reason:
        raise RuleViolation(
            "A suspension must state a reason — it locks out every user at the institution.",
            rule="suspension_requires_reason",
        )

    previous = tenant.status
    tenant.status = status
    if status == TenantStatus.SUSPENDED:
        tenant.suspended_at = utcnow()
        tenant.suspension_reason = reason
    elif previous == TenantStatus.SUSPENDED:
        tenant.suspended_at = None
        tenant.suspension_reason = None

    record_platform_event(
        control,
        action="tenant:set_status",
        resource_type="tenant",
        resource_id=str(tenant.id),
        tenant_id=tenant.id,
        summary=f"{tenant.slug}: {previous} -> {status}",
        metadata={"reason": reason},
    )
    tenant_resolver.invalidate(tenant_id=tenant.id, slug=tenant.slug)
    log.warning("tenant_status_changed", tenant=tenant.slug, from_=previous, to=status)
    return tenant


def start_impersonation(
    control: Session,
    *,
    platform_user: PlatformUser,
    tenant: Tenant,
    reason: str,
    ticket_reference: str | None,
    target_user_id: uuid.UUID | None,
    require_tenant_approval: bool,
    approved_by_id: uuid.UUID | None,
) -> tuple[ImpersonationSession, str]:
    """Open a read-only support session inside a university.

    Read-only is enforced by `baseline.impersonation-limits`, not by anything
    here — which is the right place for it, because the rule then applies to
    every endpoint including ones written later. What this function enforces is
    the front door: a stated reason, a short expiry, and where the contract
    requires it, the institution's own administrator having said yes.
    """
    if len(reason.strip()) < 15:
        raise ValidationFailed(
            "State why this support session is needed, in enough detail for the "
            "institution to review later.",
            code="reason_too_short",
        )
    if require_tenant_approval and approved_by_id is None:
        raise Forbidden(
            "This institution requires its own administrator to approve support access."
        )

    now = utcnow()
    session_row = ImpersonationSession(
        tenant_id=tenant.id,
        platform_user_id=platform_user.id,
        target_user_id=target_user_id,
        reason=reason.strip(),
        ticket_reference=ticket_reference,
        approved_by_id=approved_by_id,
        started_at=now,
        expires_at=now + timedelta(minutes=30),
    )
    control.add(session_row)
    control.flush()

    token = issue_token(
        subject_id=target_user_id or platform_user.id,
        kind="impersonation",
        tenant_id=tenant.id,
        claims={
            "knd": "staff" if target_user_id else "platform",
            "imp": str(platform_user.id),
            "isid": str(session_row.id),
        },
    )
    record_platform_event(
        control,
        action="impersonation:start",
        resource_type="impersonation",
        resource_id=str(session_row.id),
        tenant_id=tenant.id,
        summary=f"{platform_user.email} opened a support session at {tenant.slug}",
        metadata={"reason": reason, "ticket": ticket_reference},
    )
    log.warning(
        "impersonation_started",
        tenant=tenant.slug,
        platform_user=platform_user.email,
        ticket=ticket_reference,
    )
    return session_row, token


def end_impersonation(control: Session, *, session_row: ImpersonationSession) -> None:
    if session_row.ended_at is not None:
        return
    session_row.ended_at = utcnow()
    record_platform_event(
        control,
        action="impersonation:end",
        resource_type="impersonation",
        resource_id=str(session_row.id),
        tenant_id=session_row.tenant_id,
        summary="Support session ended",
        metadata={"actions_taken": session_row.actions_taken},
    )


def tenant_health(control: Session) -> list[dict[str, Any]]:
    """Fleet overview for the control plane dashboard."""
    from acmis.core.db import live_tenant_engines

    rows = control.execute(select(Tenant).order_by(Tenant.slug)).scalars().all()
    return [
        {
            "slug": t.slug,
            "name": t.name,
            "status": t.status,
            "region": t.region,
            "schema_revision": t.schema_revision,
            "policy_revision": t.policy_revision,
            "features": sorted(t.enabled_features or ()),
            "onboarded_at": t.onboarded_at.isoformat() if t.onboarded_at else None,
        }
        for t in rows
    ] + [{"_engines_live": live_tenant_engines()}]


#: Categories the platform trail uses, mirrored from the tenant one so a
#: reviewer reading both sees the same vocabulary.
PLATFORM_CATEGORY = AuditCategory.TENANCY
