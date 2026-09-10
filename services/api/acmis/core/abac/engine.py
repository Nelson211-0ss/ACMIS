"""The policy decision point.

Deny by default. A request is permitted only when some applicable rule says
`permit` and no applicable rule says `deny`. An empty bundle denies everything,
a policy that fails to load denies everything it would have granted, and an
attribute nobody populated makes a `permit` fail to match rather than
succeeding vacuously. Every one of those is the safe direction, and each was
chosen on purpose: the alternative failure mode is a deployment where marks are
world-writable because a YAML file had a tab in it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import structlog

from acmis.core.abac.expressions import ConditionError
from acmis.core.abac.policy import Combining, Effect, Policy, Rule

log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RuleTrace:
    """One rule's contribution, kept whether or not it decided the request."""

    policy_id: str
    rule_id: str
    effect: Effect
    matched: bool
    error: str | None = None


@dataclass(frozen=True, slots=True)
class Decision:
    """The answer, plus everything needed to explain and enforce it.

    The trace is not debug output. When a student appeals a withheld
    transcript, the institution has to be able to state which rule withheld it
    and on what attributes — so the trace is what the audit trail persists for
    a denial, and it is the reason this returns an object rather than a bool.
    """

    allowed: bool
    action: str
    resource_type: str
    resource_id: str | None
    #: The rule that settled it. `None` means nothing was applicable, i.e.
    #: denied by default — which reads very differently in an audit review from
    #: an explicit prohibition, so the distinction is preserved.
    deciding_policy_id: str | None = None
    deciding_rule_id: str | None = None
    reason: str = "no applicable policy"
    obligations: frozenset[str] = field(default_factory=frozenset)
    #: Union of every applicable permit's `mask_fields`. A field masked by any
    #: applicable rule stays masked; the caller does not get the more generous
    #: of two overlapping grants.
    masked_fields: frozenset[str] = field(default_factory=frozenset)
    #: Intersection of the applicable permits' `writable_fields`. `None` means
    #: unrestricted.
    writable_fields: frozenset[str] | None = None
    sensitive: bool = False
    trace: tuple[RuleTrace, ...] = ()
    #: Rules that raised while evaluating. A broken rule never grants, and this
    #: is what the health check alerts on.
    errors: tuple[str, ...] = ()

    def explain(self, *, verbose: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "allowed": self.allowed,
            "action": self.action,
            "resource_type": self.resource_type,
        }
        if verbose:
            payload |= {
                "deciding_policy": self.deciding_policy_id,
                "deciding_rule": self.deciding_rule_id,
                "reason": self.reason,
                "trace": [
                    {
                        "policy": t.policy_id,
                        "rule": t.rule_id,
                        "effect": str(t.effect),
                        "matched": t.matched,
                        "error": t.error,
                    }
                    for t in self.trace
                ],
            }
        return payload

    def filter(self, data: Mapping[str, Any]) -> dict[str, Any]:
        """Drop masked fields from a payload on the way out.

        Dropped, not nulled: `{"disability": null}` and "you may not see this"
        are different statements, and a UI that renders the first will show
        "None" where a disclosure exists.
        """
        if not self.masked_fields:
            return dict(data)
        return {k: v for k, v in data.items() if k not in self.masked_fields}

    def reject_unwritable(self, fields: Sequence[str]) -> tuple[str, ...]:
        """Which of the fields the caller tried to write it may not write."""
        if self.writable_fields is None:
            return ()
        return tuple(f for f in fields if f not in self.writable_fields)


DENY_BY_DEFAULT = Decision(
    allowed=False,
    action="",
    resource_type="",
    resource_id=None,
    reason="denied by default: no policy is applicable to this request",
)


class PolicyEngine:
    """Holds a compiled bundle and answers decisions against it.

    Immutable once built. Reloading policy replaces the whole engine behind an
    atomic reference swap (see `registry.py`) rather than mutating this one, so
    a request that started under the old bundle finishes under it — a
    half-applied policy change is worse than either version of it.
    """

    __slots__ = ("_all_actions", "_by_action", "_policies", "version")

    def __init__(self, policies: Sequence[Policy], *, version: str = "0") -> None:
        enabled = sorted((p for p in policies if p.enabled), key=lambda p: (p.priority, p.id))
        self._policies: tuple[Policy, ...] = tuple(enabled)
        self.version = version

        # Index by action so a decision touches only the relevant slice. Rules
        # with a wildcard or unrestricted target land in the catch-all bucket
        # and are always considered.
        index: dict[str, list[Policy]] = {}
        catch_all: list[Policy] = []
        for policy in self._policies:
            if not policy.target.actions:
                catch_all.append(policy)
                continue
            for pattern in policy.target.actions:
                index.setdefault(pattern, []).append(policy)
        self._by_action = (index, tuple(catch_all))
        self._all_actions = frozenset(index)

    @property
    def policies(self) -> tuple[Policy, ...]:
        return self._policies

    def candidates(self, action: str) -> list[Policy]:
        index, catch_all = self._by_action
        noun, _, _verb = action.partition(":")
        found = [*index.get(action, ()), *index.get(f"{noun}:*", ()), *catch_all]
        return sorted(found, key=lambda p: (p.priority, p.id))

    def decide(
        self,
        *,
        action: str,
        resource_type: str,
        subject: Mapping[str, Any],
        resource: Mapping[str, Any] | None = None,
        environment: Mapping[str, Any] | None = None,
        tenant: Mapping[str, Any] | None = None,
        resource_id: str | None = None,
    ) -> Decision:
        resource = resource or {}
        subject_kind = str(subject.get("kind", "anonymous"))
        module = (environment or {}).get("module")

        attrs = {
            "subject": subject,
            "resource": resource,
            "action": action,
            "environment": environment or {},
            "tenant": tenant or {},
            "context": {},
        }

        trace: list[RuleTrace] = []
        errors: list[str] = []
        permits: list[tuple[Policy, Rule]] = []
        denies: list[tuple[Policy, Rule]] = []

        for policy in self.candidates(action):
            if not policy.target.matches(
                action=action,
                resource_type=resource_type,
                subject_kind=subject_kind,
                module=module,
            ):
                continue

            local_permits: list[Rule] = []
            local_denies: list[Rule] = []

            for rule in policy.rules:
                try:
                    matched = rule.applies(**attrs)
                    error: str | None = None
                except ConditionError as exc:
                    matched, error = False, str(exc)
                    errors.append(f"{policy.id}/{rule.id}: {exc}")
                    log.error("abac_rule_error", policy=policy.id, rule=rule.id, error=str(exc))

                trace.append(RuleTrace(policy.id, rule.id, rule.effect, matched, error))
                if not matched:
                    continue
                (local_denies if rule.effect is Effect.DENY else local_permits).append(rule)

                if policy.combining is Combining.FIRST_APPLICABLE:
                    break

            # Resolve *within* the policy first, then contribute upward. This
            # is what makes a policy a unit: a policy that internally decides
            # "deny" does not also hand a permit to the outer combination.
            if policy.combining is Combining.PERMIT_OVERRIDES:
                if local_permits:
                    permits.extend((policy, r) for r in local_permits)
                elif local_denies:
                    denies.extend((policy, r) for r in local_denies)
            elif local_denies:
                denies.extend((policy, r) for r in local_denies)
            else:
                permits.extend((policy, r) for r in local_permits)

        # --- Global combination: deny overrides, with named exceptions ------
        if denies:
            # A PERMIT_OVERRIDES policy that matched lifts only the specific
            # prohibitions it named. Everything else it did not name still
            # denies, so a delegated exception cannot widen into a general one.
            overridden_ids = {
                target
                for policy, _rule in permits
                if policy.combining is Combining.PERMIT_OVERRIDES
                for target in policy.overrides
            }
            surviving = [(p, r) for (p, r) in denies if p.id not in overridden_ids]
            if surviving:
                policy, rule = surviving[0]
                return Decision(
                    allowed=False,
                    action=action,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    deciding_policy_id=policy.id,
                    deciding_rule_id=rule.id,
                    reason=rule.description or f"denied by {policy.id}/{rule.id}",
                    sensitive=rule.sensitive,
                    trace=tuple(trace),
                    errors=tuple(errors),
                )

        if not permits:
            return Decision(
                allowed=False,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                reason=DENY_BY_DEFAULT.reason,
                trace=tuple(trace),
                errors=tuple(errors),
            )

        policy, rule = permits[0]
        masked: set[str] = set()
        obligations: set[str] = set()
        writable: set[str] | None = None
        sensitive = False

        unrestricted_write = False
        for _p, r in permits:
            masked.update(r.mask_fields)
            obligations.update(r.obligations)
            sensitive = sensitive or r.sensitive
            if r.writable_fields:
                writable = (
                    set(r.writable_fields)
                    if writable is None
                    else writable | set(r.writable_fields)
                )
            else:
                # A rule with no field restriction grants every field the
                # schema allows. Field grants union rather than intersect: two
                # applicable permits are two independent grounds to act, and
                # intersecting them would make holding an extra role *narrow*
                # what someone may edit. Masking, which is a restriction, goes
                # the other way and unions the prohibitions.
                unrestricted_write = True
        if unrestricted_write:
            writable = None

        return Decision(
            allowed=True,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            deciding_policy_id=policy.id,
            deciding_rule_id=rule.id,
            reason=rule.description or f"permitted by {policy.id}/{rule.id}",
            obligations=frozenset(obligations),
            masked_fields=frozenset(masked),
            writable_fields=frozenset(writable) if writable is not None else None,
            sensitive=sensitive,
            trace=tuple(trace),
            errors=tuple(errors),
        )

    def lint(self) -> list[str]:
        """Static checks a bundle must pass before it is served.

        Run in CI and on load. Catches the mistakes that produce a bundle which
        loads cleanly and then behaves nothing like its author intended.
        """
        problems: list[str] = []
        seen_policies: set[str] = set()
        for policy in self._policies:
            if policy.id in seen_policies:
                problems.append(f"duplicate policy id {policy.id!r}")
            seen_policies.add(policy.id)

            seen_rules: set[str] = set()
            for rule in policy.rules:
                if rule.id in seen_rules:
                    problems.append(f"{policy.id}: duplicate rule id {rule.id!r}")
                seen_rules.add(rule.id)
                if (
                    rule.effect is Effect.PERMIT
                    and rule.condition is None
                    and not policy.target.actions
                ):
                    problems.append(
                        f"{policy.id}/{rule.id}: unconditional permit with no action "
                        "target — this grants everything to everyone"
                    )
                if rule.mask_fields and rule.effect is Effect.DENY:
                    problems.append(
                        f"{policy.id}/{rule.id}: mask_fields on a deny rule has no effect"
                    )
            for target in policy.overrides:
                if target not in seen_policies and target not in {p.id for p in self._policies}:
                    problems.append(f"{policy.id}: overrides unknown policy {target!r}")
        return problems
