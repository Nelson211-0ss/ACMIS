"""Working out which university a request belongs to.

Resolution order, most trustworthy first:

1. The `tid` claim on a verified access token. Signed by us, so it cannot be
   edited by the caller.
2. The `Host` header — `juba.acmis.ac.ug` -> `juba`. Used for unauthenticated
   requests: sign-in, the public application form, certificate verification.
3. `X-ACMIS-Tenant`, and only in `local`/`test`. Nine dev servers on
   `localhost` share one host name, so development needs a header; production
   must not honour one, or a signed-in user at one university can address
   another's database by editing a request.

When both a token claim and a host are present and they disagree, the request
is refused rather than reconciled. Picking either one is a guess, and the
guesses are respectively "let a stale token read the wrong database" and "let a
header override a signature".

Tenant records are cached briefly. Without it every request costs a
control-plane query, and with a long TTL a suspension takes minutes to bite —
30 seconds is short enough that "we have locked them out" is true by the time
the sentence finishes.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from acmis.core.config import settings
from acmis.core.context import TenantContext
from acmis.core.errors import TenantNotResolved, TenantSuspended

log = structlog.get_logger(__name__)

CACHE_TTL_SECONDS = 30


@dataclass(slots=True)
class _Entry:
    tenant: TenantContext
    status: str
    expires_at: float
    policy_revision: int


class TenantCache:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._by_slug: dict[str, _Entry] = {}
        self._by_id: dict[uuid.UUID, _Entry] = {}

    def get_by_slug(self, slug: str) -> _Entry | None:
        return self._fresh(self._by_slug.get(slug))

    def get_by_id(self, tenant_id: uuid.UUID) -> _Entry | None:
        return self._fresh(self._by_id.get(tenant_id))

    def put(self, entry: _Entry) -> None:
        with self._lock:
            self._by_slug[entry.tenant.slug] = entry
            self._by_id[entry.tenant.id] = entry

    def evict(self, *, slug: str | None = None, tenant_id: uuid.UUID | None = None) -> None:
        with self._lock:
            if slug:
                entry = self._by_slug.pop(slug, None)
                if entry:
                    self._by_id.pop(entry.tenant.id, None)
            if tenant_id:
                entry = self._by_id.pop(tenant_id, None)
                if entry:
                    self._by_slug.pop(entry.tenant.slug, None)

    def clear(self) -> None:
        with self._lock:
            self._by_slug.clear()
            self._by_id.clear()

    @staticmethod
    def _fresh(entry: _Entry | None) -> _Entry | None:
        if entry is None:
            return None
        return entry if entry.expires_at > time.monotonic() else None


cache = TenantCache()


def slug_from_host(host: str | None) -> str | None:
    """`juba.acmis.ac.ug:8000` -> `juba`. Returns None when the host names no tenant.

    Only a host under the configured suffix yields a slug. That strictness is
    the point: an earlier version fell back to "the first label of any dotted
    host", which turned `127.0.0.1:8000` into the slug `127` and then refused
    every development request — because a wrong-but-truthy slug takes
    precedence over the `X-ACMIS-Tenant` header, by design.

    A wrong slug is worse than no slug. No slug lets the header (in
    development) or an explicit error (in production) decide; a wrong one
    silently addresses a database that does not exist, or — much worse on a
    shared cluster — one that does.
    """
    if not host:
        return None
    hostname = host.split(":", 1)[0].lower().strip(".")
    if not hostname or hostname == settings.control_plane_host:
        return None

    suffix = settings.tenant_host_suffix.lower()
    if not hostname.endswith("." + suffix):
        # Includes `localhost`, a bare IP, and any host outside the deployment's
        # own domain.
        return None

    candidate = hostname[: -(len(suffix) + 1)]
    # `admissions.juba.acmis.ac.ug` -> the label nearest the suffix, so a
    # per-module subdomain still resolves to its university.
    return candidate.rsplit(".", 1)[-1] or None


def resolve(
    session: Session,
    *,
    slug: str | None = None,
    tenant_id: uuid.UUID | None = None,
) -> tuple[TenantContext, int]:
    """Load a tenant and its policy revision. Raises if unusable."""
    if not slug and not tenant_id:
        raise TenantNotResolved()

    entry = cache.get_by_id(tenant_id) if tenant_id else cache.get_by_slug(slug or "")
    if entry is None:
        entry = _load(session, slug=slug, tenant_id=tenant_id)

    if entry.status == "suspended":
        raise TenantSuspended()
    if entry.status in {"provisioning", "failed"}:
        raise TenantNotResolved(
            "This institution is still being set up.", code="tenant_provisioning"
        )
    return entry.tenant, entry.policy_revision


def _load(session: Session, *, slug: str | None, tenant_id: uuid.UUID | None) -> _Entry:
    from acmis.modules.tenancy.models import Tenant  # local: avoids a cycle

    stmt = select(Tenant)
    stmt = stmt.where(Tenant.id == tenant_id) if tenant_id else stmt.where(Tenant.slug == slug)
    tenant = session.execute(stmt).scalar_one_or_none()
    if tenant is None:
        # Same message whichever way it failed. "No such institution" versus
        # "that institution is suspended" is an information leak about the
        # platform's customer list.
        raise TenantNotResolved()

    entry = _Entry(
        tenant=TenantContext(
            id=tenant.id,
            slug=tenant.slug,
            name=tenant.name,
            database=tenant.database_name,
            dsn=settings.tenant_dsn(tenant.database_name),
            locale=tenant.locale,
            timezone=tenant.timezone,
            currency=tenant.currency,
            features=frozenset(tenant.enabled_features or ()),
            settings=dict(tenant.runtime_settings or {}),
        ),
        status=tenant.status,
        expires_at=time.monotonic() + CACHE_TTL_SECONDS,
        policy_revision=tenant.policy_revision,
    )
    cache.put(entry)
    return entry


def resolve_from_request(
    session: Session,
    *,
    host: str | None,
    token_tenant_id: uuid.UUID | None,
    header_slug: str | None,
) -> tuple[TenantContext, int] | None:
    """Apply the precedence rules above. `None` means the control plane."""
    host_slug = slug_from_host(host)

    if header_slug and settings.environment not in {"local", "test"}:
        log.warning("tenant_header_ignored", host=host, header=header_slug)
        header_slug = None

    if token_tenant_id is not None:
        tenant, revision = resolve(session, tenant_id=token_tenant_id)
        if host_slug and host_slug != tenant.slug:
            log.error("tenant_mismatch", host_slug=host_slug, token_tenant=str(tenant.slug))
            raise TenantNotResolved(
                "This session belongs to a different institution.",
                code="tenant_mismatch",
            )
        return tenant, revision

    slug = host_slug or header_slug
    if not slug:
        return None
    return resolve(session, slug=slug)


def invalidate(**kwargs: Any) -> None:
    """Called whenever a tenant record changes so the change takes effect now."""
    cache.evict(**kwargs)
