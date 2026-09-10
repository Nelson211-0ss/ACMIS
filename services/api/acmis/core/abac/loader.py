"""Loading policy bundles from disk and from tenant overlays.

Two layers, in this order:

1. **Builtin** — YAML shipped in `acmis/policies/`. These encode the rules that
   are true of any university running ACMIS: an examiner may not approve their
   own marks, a student may read only their own record, a suspended account may
   do nothing. They are versioned with the code and a tenant cannot delete
   them.
2. **Tenant overlay** — rows in the tenant database's `abac_policy` table,
   authored by that university's system administrator. Universities genuinely
   differ here: one delegates fee waivers to faculty deans, another reserves
   them to the bursar; one lets heads of department see all marks in their
   department, another only after the board of examiners sits.

An overlay may *add* policies and may *tighten* builtin ones by adding deny
rules. It may not remove a builtin deny — the loader refuses an overlay policy
whose id collides with a builtin one. Without that rule, "multi-tenant
configurability" becomes "any tenant admin can switch off separation of
duties", and the separation of duties is the part an auditor came to see.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import structlog
import yaml

from acmis.core.abac.engine import PolicyEngine
from acmis.core.abac.expressions import ConditionError
from acmis.core.abac.policy import Effect, Policy

log = structlog.get_logger(__name__)


class PolicyLoadError(RuntimeError):
    """A bundle that will not load. Fatal at boot, non-fatal on reload.

    At boot the process refuses to start: serving requests with a bundle that
    is missing rules means silently running with less authorization than the
    deployment declares. On a hot reload the previous engine is kept instead,
    because a typo in an overlay must not take a university offline.
    """


def load_builtin_policies(policy_dir: str | Path) -> list[Policy]:
    directory = Path(policy_dir)
    if not directory.exists():
        raise PolicyLoadError(f"policy directory {directory} does not exist")

    policies: list[Policy] = []
    problems: list[str] = []
    for path in sorted(directory.rglob("*.yaml")):
        try:
            documents = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
        except yaml.YAMLError as exc:
            problems.append(f"{path.name}: {exc}")
            continue
        for document in documents:
            if not document:
                continue
            for raw in _as_policy_list(document):
                try:
                    policies.append(Policy.from_dict(raw, source="builtin"))
                except (ConditionError, KeyError, ValueError) as exc:
                    problems.append(f"{path.name}: {exc}")

    if problems:
        raise PolicyLoadError("policy bundle did not load:\n  - " + "\n  - ".join(problems))
    log.info("abac_builtin_loaded", count=len(policies), directory=str(directory))
    return policies


def _as_policy_list(document: Any) -> Iterable[dict[str, Any]]:
    """Accept either a single policy or `{policies: [...]}` per file."""
    if isinstance(document, dict) and "policies" in document:
        return document["policies"] or ()
    if isinstance(document, list):
        return document
    if isinstance(document, dict):
        return (document,)
    raise ConditionError(f"unexpected policy document of type {type(document).__name__}")


def load_overlay_policies(
    rows: Sequence[Any], *, tenant_slug: str, builtin_ids: frozenset[str]
) -> tuple[list[Policy], list[str]]:
    """Compile tenant overlay rows. Returns (policies, problems).

    Never raises: one broken overlay row must not deny an entire university.
    The row is skipped, the problem is returned for the health endpoint and the
    audit trail, and the rest of the overlay still applies.
    """
    policies: list[Policy] = []
    problems: list[str] = []
    source = f"tenant:{tenant_slug}"

    for row in rows:
        document = row.document if hasattr(row, "document") else row
        policy_id = str(document.get("id", "<unnamed>"))
        if policy_id in builtin_ids:
            problems.append(
                f"{policy_id}: an overlay may not replace a builtin policy; "
                "add a separate policy with its own id to tighten this"
            )
            continue
        try:
            policy = Policy.from_dict(document, source=source)
        except (ConditionError, KeyError, ValueError) as exc:
            problems.append(f"{policy_id}: {exc}")
            continue
        if any(r.effect is Effect.PERMIT for r in policy.rules) and policy.priority < 50:
            # Priority < 50 is reserved for prohibitions so that FIRST_APPLICABLE
            # sets and the decision log stay readable.
            problems.append(f"{policy_id}: priority below 50 is reserved for deny policies")
            continue
        policies.append(policy)

    if problems:
        log.warning("abac_overlay_problems", tenant=tenant_slug, problems=problems)
    return policies, problems


def build_engine(policies: Sequence[Policy]) -> PolicyEngine:
    engine = PolicyEngine(policies, version=bundle_version(policies))
    problems = engine.lint()
    if problems:
        log.warning("abac_lint", problems=problems)
    return engine


def bundle_version(policies: Sequence[Policy]) -> str:
    """Stable fingerprint of a bundle.

    Written onto every decision in the audit trail. Two years later, "why was
    this permitted" is answerable only if you can identify exactly which
    version of which rules were loaded at the time.
    """
    digest = hashlib.sha256()
    for policy in sorted(policies, key=lambda p: p.id):
        digest.update(f"{policy.id}:{policy.version}:{policy.source}:{policy.enabled}".encode())
        for rule in policy.rules:
            digest.update(
                f"|{rule.id}:{rule.effect}:{rule.condition.source if rule.condition else ''}"
                f":{','.join(rule.mask_fields)}".encode()
            )
    return digest.hexdigest()[:16]
