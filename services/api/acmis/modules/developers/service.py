"""API client authentication and the machine principal."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from acmis.core.audit import AuditCategory, emit
from acmis.core.context import Principal, current_context
from acmis.core.errors import Unauthenticated
from acmis.core.models import utcnow
from acmis.core.security import hash_secret, new_api_key
from acmis.modules.developers.models import ApiClient, ApiKey, IntegrationLog

log = structlog.get_logger(__name__)


def principal_for_api_key(session: Session, *, api_key: str, tenant_id: uuid.UUID) -> Principal:
    """Resolve an API key to a service principal.

    The intersection rule is implemented here, and it is the module's whole
    security position: the principal's `permissions` are its **owner's**
    permissions, and its `scopes` are what the client was granted. A policy
    that requires a permission the owner lacks fails whatever the token's
    scopes say, and `developers.machine-tokens/scope-must-cover-action`
    separately requires the scope. Both must hold.
    """
    row = session.execute(
        select(ApiKey)
        .options(selectinload(ApiKey.client))
        .where(ApiKey.key_hash == hash_secret(api_key))
    ).scalar_one_or_none()

    generic = Unauthenticated("That API key is not valid.")
    if row is None or not row.is_live:
        raise generic

    client = row.client
    if client is None or client.status != "active" or client.deleted_at is not None:
        raise generic

    now = utcnow()
    row.last_used_at = now
    row.use_count += 1
    ctx = current_context()
    row.last_used_ip = ctx.ip_address if ctx else None
    client.last_used_at = now

    if (
        client.allowed_ip_ranges
        and ctx
        and ctx.ip_address
        and not _ip_allowed(ctx.ip_address, client.allowed_ip_ranges)
    ):
        log.warning("api_key_ip_rejected", client=client.client_id, ip=ctx.ip_address)
        raise generic

    owner_permissions = _owner_permissions(session, client.owner_id)
    # A key's own scopes may narrow the client's grant, never widen it.
    scopes = set(row.scopes or client.granted_scopes or ())
    scopes &= set(client.granted_scopes or scopes)

    return Principal(
        id=client.owner_id,
        kind="service",
        display_name=f"client:{client.name}",
        email=client.owner_email,
        tenant_id=tenant_id,
        roles=frozenset({"service"}),
        permissions=frozenset(owner_permissions),
        scopes=frozenset(scopes),
        mfa_satisfied=False,
        extra={
            "status": "active",
            "client_id": client.client_id,
            "environment": client.environment,
            "api_key_id": str(row.id),
        },
    )


def _owner_permissions(session: Session, owner_id: uuid.UUID) -> set[str]:
    from acmis.modules.identity.models import RoleAssignment, UserAccount

    account = session.execute(
        select(UserAccount)
        .options(selectinload(UserAccount.assignments).joinedload(RoleAssignment.role))
        .where(UserAccount.id == owner_id, UserAccount.deleted_at.is_(None))
    ).scalar_one_or_none()
    if account is None or not account.is_usable:
        # An integration whose owner has left the institution stops working.
        # Abrupt, and correct: the alternative is a live credential with
        # nobody answerable for it.
        raise Unauthenticated("The account this key belongs to is no longer active.")

    today = date.today()
    permissions: set[str] = set()
    for assignment in account.assignments:
        if assignment.is_active_on(today) and assignment.role is not None:
            permissions.update(assignment.role.permission_codes or ())
    return permissions


def _ip_allowed(address: str, ranges: list[str]) -> bool:
    import ipaddress

    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    for entry in ranges:
        try:
            if ip in ipaddress.ip_network(entry, strict=False):
                return True
        except ValueError:
            continue
    return False


def create_api_key(
    session: Session,
    *,
    client: ApiClient,
    name: str,
    scopes: list[str] | None,
    ttl_days: int = 365,
    created_by_id: uuid.UUID,
) -> tuple[ApiKey, str]:
    """Mint a key. The plaintext is returned here and never again.

    Deliberately the only moment the full key exists in a response.
    `developers.credentials/never-reveal` refuses every later read, so a
    compromised console session cannot harvest the credentials of existing
    integrations.
    """
    full, prefix, digest = new_api_key(environment=client.environment)
    granted = set(client.granted_scopes or ())
    requested = set(scopes or granted)
    effective = sorted(requested & granted) if granted else []

    row = ApiKey(
        client_id=client.id,
        name=name,
        prefix=prefix,
        key_hash=digest,
        environment=client.environment,
        scopes=effective,
        created_by_id=created_by_id,
        expires_at=utcnow() + timedelta(days=ttl_days),
    )
    session.add(row)
    session.flush()
    emit(
        "api_key:create",
        AuditCategory.INTEGRATION,
        resource_type="api_key",
        resource_id=row.id,
        resource_label=f"{name} ({prefix}…)",
        summary=f"API key issued for client {client.client_id}",
        metadata={"prefix": prefix, "scopes": effective, "expires_at": str(row.expires_at)},
        severity="notice",
    )
    return row, full


def rotate_api_key(
    session: Session, *, key: ApiKey, actor_id: uuid.UUID, grace_hours: int = 24
) -> tuple[ApiKey, str]:
    """Issue a replacement, leaving the old one valid for a grace window.

    Without the overlap, rotating a credential means an outage between the new
    key being minted and the integration being redeployed with it — so nobody
    rotates, and keys live for years.
    """
    client = key.client
    if client is None:  # pragma: no cover
        raise Unauthenticated("That key's client no longer exists.")

    replacement, plaintext = create_api_key(
        session,
        client=client,
        name=f"{key.name} (rotated)",
        scopes=list(key.scopes or ()),
        created_by_id=actor_id,
    )
    replacement.rotated_from_id = key.id
    key.rotation_grace_until = utcnow() + timedelta(hours=grace_hours)
    key.expires_at = key.rotation_grace_until
    emit(
        "api_key:rotate",
        AuditCategory.INTEGRATION,
        resource_type="api_key",
        resource_id=key.id,
        summary=f"Key rotated; previous key valid for {grace_hours}h",
        severity="notice",
    )
    return replacement, plaintext


def revoke_api_key(session: Session, *, key: ApiKey, actor_id: uuid.UUID, reason: str) -> None:
    key.revoked_at = utcnow()
    key.revoked_by_id = actor_id
    key.revocation_reason = reason
    emit(
        "api_key:revoke",
        AuditCategory.INTEGRATION,
        resource_type="api_key",
        resource_id=key.id,
        summary=f"Key revoked: {reason}",
        severity="warning",
    )


def log_integration_call(
    session: Session,
    *,
    client_id: uuid.UUID | None,
    api_key_id: uuid.UUID | None,
    status_code: int,
    duration_ms: int | None,
    denied_reason: str | None = None,
    response_bytes: int | None = None,
) -> None:
    """The developer's own log line. Never the request body.

    A developer needs to see the request line, the status and the timing to
    debug their integration. They do not need the payload, and a log their
    whole team can read is the wrong place for one student's marks.
    """
    ctx = current_context()
    if ctx is None:
        return
    session.add(
        IntegrationLog(
            client_id=client_id,
            api_key_id=api_key_id,
            request_id=ctx.request_id,
            occurred_at=utcnow(),
            method=ctx.method,
            path=ctx.path[:300],
            status_code=status_code,
            duration_ms=duration_ms,
            denied_reason=denied_reason,
            ip_address=ctx.ip_address,
            user_agent=(ctx.user_agent or "")[:300] or None,
            response_bytes=response_bytes,
        )
    )


def client_id_for(name: str) -> str:
    """A public, non-guessable client identifier."""
    return f"acmis_{uuid.uuid4().hex[:20]}"


def summarise_usage(session: Session, *, client_id: uuid.UUID, days: int = 7) -> dict[str, Any]:
    """Call volume, error rate and the slowest paths, for the portal dashboard."""
    from sqlalchemy import case, func

    since = utcnow() - timedelta(days=days)
    rows = session.execute(
        select(
            IntegrationLog.path,
            func.count().label("calls"),
            func.avg(IntegrationLog.duration_ms).label("avg_ms"),
            # `COUNT` over a CASE rather than a cast sum: it says what it
            # means and does not depend on how the driver renders a boolean.
            func.count(case((IntegrationLog.status_code >= 400, 1))).label("errors"),
        )
        .where(IntegrationLog.client_id == client_id, IntegrationLog.occurred_at >= since)
        .group_by(IntegrationLog.path)
        .order_by(func.count().desc())
        .limit(20)
    ).all()
    return {
        "window_days": days,
        "paths": [
            {
                "path": r.path,
                "calls": int(r.calls or 0),
                "avg_ms": round(float(r.avg_ms or 0), 1),
                "errors": int(r.errors or 0),
            }
            for r in rows
        ],
    }
