"""The policy enforcement point.

One function — `authorize()` — is the only way anything in ACMIS checks
permission, and it always does three things together: decide, log, and (on
denial) raise. Bundling them is the point. The failure mode in every system
that separates them is a code path that decides and forgets to log, or checks
and forgets to raise, and both are invisible until someone asks the system to
account for itself.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from typing import Any

import structlog

from acmis.core.abac import resources
from acmis.core.abac.engine import Decision, PolicyEngine
from acmis.core.audit import AuditCategory, AuditOutcome, AuditRecord, emit
from acmis.core.config import settings
from acmis.core.context import RequestContext, require_context
from acmis.core.errors import Forbidden, ValidationFailed

log = structlog.get_logger(__name__)

#: Actions whose *reads* are logged, not just their writes. Everything that
#: touches a person's special-category data or the integrity of an award.
LOGGED_READ_ACTIONS = frozenset(
    {
        "student:read_sensitive",
        "student:read_medical",
        "student:read_disciplinary",
        "applicant:read_sensitive",
        "result:read_unpublished",
        "transcript:read",
        "transcript:issue",
        "award:read",
        "student_ledger:read_statement",
        "staff:read_payroll",
        "audit:read",
        "export:run",
    }
)


def decide(
    *,
    engine: PolicyEngine,
    action: str,
    resource_type: str,
    resource: Any = None,
    resource_id: str | uuid.UUID | None = None,
    extra_attributes: Mapping[str, Any] | None = None,
    context: RequestContext | None = None,
) -> Decision:
    """Ask the engine. No logging, no raising — use `authorize()` instead.

    Public because the UI needs bulk "what may I do here" answers to decide
    which buttons to render, and rendering a button the user cannot use is a
    worse experience than not rendering it.
    """
    ctx = context or require_context()
    attributes = resources.describe(resource_type, resource)
    if extra_attributes:
        attributes.update(extra_attributes)

    tenant_attrs: dict[str, Any] = {}
    if ctx.tenant is not None:
        tenant_attrs = {
            "id": str(ctx.tenant.id),
            "slug": ctx.tenant.slug,
            "features": sorted(ctx.tenant.features),
            **ctx.tenant.settings,
        }

    rid = str(resource_id) if resource_id else attributes.get("id")
    return engine.decide(
        action=action,
        resource_type=resource_type,
        subject=ctx.principal.attributes(),
        resource=attributes,
        environment=ctx.environment(),
        tenant=tenant_attrs,
        resource_id=rid,
    )


def authorize(
    *,
    engine: PolicyEngine,
    action: str,
    resource_type: str,
    resource: Any = None,
    resource_id: str | uuid.UUID | None = None,
    extra_attributes: Mapping[str, Any] | None = None,
    category: AuditCategory = AuditCategory.AUTHORIZATION,
    audit_reads: bool | None = None,
) -> Decision:
    """Decide, log, and raise `Forbidden` on denial.

    Returns the `Decision` on success because the caller still needs it: the
    field mask has to be applied to the response and the writable-field set has
    to be checked against the payload. A caller that ignores the return value
    has enforced the yes/no and skipped the field-level half.
    """
    ctx = require_context()
    decision = decide(
        engine=engine,
        action=action,
        resource_type=resource_type,
        resource=resource,
        resource_id=resource_id,
        extra_attributes=extra_attributes,
        context=ctx,
    )

    if decision.errors:
        # A rule that raised did not grant, but it also did not do its job. It
        # is logged at error level with the policy id so it is fixed rather
        # than discovered later as an unexplained denial.
        log.error(
            "abac_decision_degraded",
            action=action,
            resource_type=resource_type,
            errors=list(decision.errors),
        )

    if not decision.allowed:
        _log_denial(decision, category=category, resource=resource, resource_type=resource_type)
        raise Forbidden(details=decision.explain(verbose=settings.explain_denials))

    should_log = audit_reads if audit_reads is not None else action in LOGGED_READ_ACTIONS
    if should_log or decision.sensitive:
        emit(
            action,
            category,
            resource_type=resource_type,
            resource_id=decision.resource_id,
            resource_label=resources.label_for(resource_type, resource),
            outcome=AuditOutcome.SUCCESS,
            summary=decision.reason,
            metadata={"policy": decision.deciding_policy_id, "rule": decision.deciding_rule_id},
            severity="notice" if decision.sensitive else "info",
        )

    log.debug(
        "abac_permit",
        action=action,
        resource_type=resource_type,
        policy=decision.deciding_policy_id,
        rule=decision.deciding_rule_id,
    )
    return decision


def enforce_writable(decision: Decision, payload: Mapping[str, Any]) -> None:
    """Refuse a write that touches fields the decision did not grant.

    Field-level authorization is where most real systems leak. The endpoint
    checks "may this person update this student" and then applies the whole
    request body, so a hall warden with a legitimate `student:update` grant for
    residence data also rewrites the sponsor and the programme. The decision
    already carries the answer; this is the line that uses it.
    """
    offered = [k for k, v in payload.items() if v is not None]
    rejected = decision.reject_unwritable(offered)
    if rejected:
        raise ValidationFailed(
            "You may not change these fields.",
            code="fields_not_writable",
            details={"fields": list(rejected)},
        )


def _log_denial(
    decision: Decision,
    *,
    category: AuditCategory,
    resource: Any,
    resource_type: str,
) -> None:
    """Every denial is recorded. This is not optional.

    A denial is the signal that matters most in an access review: one is a
    mis-set role, two hundred against different students in ten minutes is
    someone walking the record set. Recorded with the deciding policy so the
    review can distinguish "the rules refused this" from "nothing applied",
    which are different problems with different fixes.
    """
    emit(
        decision.action,
        category,
        resource_type=resource_type,
        resource_id=decision.resource_id,
        resource_label=resources.label_for(resource_type, resource),
        outcome=AuditOutcome.DENIED,
        summary=decision.reason,
        metadata={
            "policy": decision.deciding_policy_id,
            "rule": decision.deciding_rule_id,
            "denied_by_default": decision.deciding_policy_id is None,
            "rule_errors": list(decision.errors),
        },
        severity="warning",
    )
    log.warning(
        "abac_deny",
        action=decision.action,
        resource_type=decision.resource_type,
        resource_id=decision.resource_id,
        policy=decision.deciding_policy_id,
        rule=decision.deciding_rule_id,
        default_deny=decision.deciding_policy_id is None,
    )


def bulk_decide(
    *,
    engine: PolicyEngine,
    actions: Sequence[str],
    resource_type: str,
    resource: Any = None,
) -> dict[str, bool]:
    """`{"result:enter": True, "result:approve": False}` for UI capability maps.

    Not audited: asking whether a button should be drawn is not an access to
    the record, and logging it would bury the accesses that matter under
    thousands of page renders.
    """
    return {
        action: decide(
            engine=engine, action=action, resource_type=resource_type, resource=resource
        ).allowed
        for action in actions
    }


def audit_record_for_denial(decision: Decision, *, category: AuditCategory) -> AuditRecord:
    """Standalone record for a denial that must be written outside a request
    transaction (see `AuditWriter`'s note on denials)."""
    return AuditRecord(
        action=decision.action,
        category=category,
        resource_type=decision.resource_type,
        resource_id=decision.resource_id,
        outcome=AuditOutcome.DENIED,
        summary=decision.reason,
        decision_policy_id=decision.deciding_policy_id,
        decision_rule_id=decision.deciding_rule_id,
        severity="warning",
    )
