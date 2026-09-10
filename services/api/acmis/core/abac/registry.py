"""Per-tenant policy engines, swapped atomically.

The builtin bundle is loaded once at boot. A tenant's effective engine is
builtin + that tenant's overlay, cached until the overlay changes. Reload is a
whole-object replacement under a lock; readers take the reference without one,
so a decision never sees a half-updated bundle and the hot path stays free of
contention.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import structlog

from acmis.core.abac.engine import PolicyEngine
from acmis.core.abac.loader import (
    build_engine,
    load_builtin_policies,
    load_overlay_policies,
)
from acmis.core.abac.policy import Policy
from acmis.core.config import settings

log = structlog.get_logger(__name__)


@dataclass(slots=True)
class TenantBundle:
    engine: PolicyEngine
    overlay_revision: int
    problems: tuple[str, ...]


class PolicyRegistry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._builtin: tuple[Policy, ...] = ()
        self._builtin_ids: frozenset[str] = frozenset()
        self._default: PolicyEngine | None = None
        self._tenants: dict[uuid.UUID, TenantBundle] = {}

    def load_builtin(self) -> None:
        policies = load_builtin_policies(settings.policy_dir)
        with self._lock:
            self._builtin = tuple(policies)
            self._builtin_ids = frozenset(p.id for p in policies)
            self._default = build_engine(policies)
            self._tenants.clear()
        log.info(
            "abac_registry_loaded",
            policies=len(policies),
            version=self._default.version if self._default else None,
        )

    @property
    def builtin_ids(self) -> frozenset[str]:
        return self._builtin_ids

    def default_engine(self) -> PolicyEngine:
        engine = self._default
        if engine is None:  # pragma: no cover - boot order bug
            raise RuntimeError("policy registry used before load_builtin()")
        return engine

    def engine_for(
        self,
        tenant_id: uuid.UUID | None,
        *,
        overlay_rows: Sequence[Any] | None = None,
        overlay_revision: int = 0,
        tenant_slug: str = "",
    ) -> PolicyEngine:
        if tenant_id is None:
            return self.default_engine()

        cached = self._tenants.get(tenant_id)
        if cached is not None and cached.overlay_revision == overlay_revision:
            return cached.engine
        if overlay_rows is None:
            # Caller has no overlay to hand and none is cached: the builtin
            # bundle alone is the correct answer, and it is the safe one.
            return cached.engine if cached else self.default_engine()

        overlay, problems = load_overlay_policies(
            overlay_rows, tenant_slug=tenant_slug, builtin_ids=self._builtin_ids
        )
        engine = build_engine([*self._builtin, *overlay])
        with self._lock:
            self._tenants[tenant_id] = TenantBundle(
                engine=engine, overlay_revision=overlay_revision, problems=tuple(problems)
            )
        log.info(
            "abac_tenant_bundle_built",
            tenant=tenant_slug,
            overlay=len(overlay),
            version=engine.version,
            problems=len(problems),
        )
        return engine

    def invalidate(self, tenant_id: uuid.UUID) -> None:
        with self._lock:
            self._tenants.pop(tenant_id, None)

    def problems_for(self, tenant_id: uuid.UUID | None) -> tuple[str, ...]:
        if tenant_id is None:
            return ()
        bundle = self._tenants.get(tenant_id)
        return bundle.problems if bundle else ()


registry = PolicyRegistry()
