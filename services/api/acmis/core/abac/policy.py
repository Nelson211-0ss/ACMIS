"""Policy model — what a rule *is*, before anything evaluates it.

Modelled on XACML's vocabulary (policy set / policy / rule / target /
condition / obligation) because that vocabulary already has answers for the
questions that come up on day two: what happens when two rules disagree, how
do you scope a rule cheaply before evaluating it, and how does a decision
carry instructions back to the caller. The wire format is YAML rather than
XACML's XML, and the combining algorithm is fixed rather than pluggable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Self

from acmis.core.abac.expressions import Condition, ConditionError, compile_condition


class Effect(StrEnum):
    PERMIT = "permit"
    DENY = "deny"


class Combining(StrEnum):
    """How disagreement between rules is settled.

    `DENY_OVERRIDES` is the default and the only one used for anything that
    touches student data: one applicable `deny` beats any number of `permit`s.
    That is what makes a restriction — "no marks may be changed after Senate
    approves the results" — actually a restriction, rather than something a
    later, broader `permit` can undo by accident.

    `PERMIT_OVERRIDES` exists for the narrow case of delegated authority, where
    an explicit grant is meant to lift a general prohibition (an appeals
    committee reopening a locked mark). A policy set using it must name the
    prohibition it is allowed to override, so the exception is visible.
    """

    DENY_OVERRIDES = "deny_overrides"
    PERMIT_OVERRIDES = "permit_overrides"
    FIRST_APPLICABLE = "first_applicable"


@dataclass(frozen=True, slots=True)
class Target:
    """Cheap pre-filter: does this policy even concern the request?

    Evaluated with set membership before any condition runs. With a few hundred
    rules loaded, the target is what keeps a decision from compiling through
    every rule in the bundle on every request. Empty collection means "any".
    """

    actions: frozenset[str] = field(default_factory=frozenset)
    resource_types: frozenset[str] = field(default_factory=frozenset)
    subject_kinds: frozenset[str] = field(default_factory=frozenset)
    modules: frozenset[str] = field(default_factory=frozenset)

    def matches(
        self, *, action: str, resource_type: str, subject_kind: str, module: str | None
    ) -> bool:
        if self.actions and not _action_matches(action, self.actions):
            return False
        if self.resource_types and resource_type not in self.resource_types:
            return False
        if self.subject_kinds and subject_kind not in self.subject_kinds:
            return False
        return not (self.modules and (module or "") not in self.modules)


def _action_matches(action: str, patterns: frozenset[str]) -> bool:
    """Exact match, or a `noun:*` wildcard.

    Only a trailing wildcard on the verb is supported. `result:*` is a
    legitimate thing to write for an examinations officer; `*:approve` is not,
    because "approve anything" is never a grant anybody should make in one
    line.
    """
    if action in patterns:
        return True
    noun, _, _verb = action.partition(":")
    return f"{noun}:*" in patterns


@dataclass(frozen=True, slots=True)
class Rule:
    id: str
    effect: Effect
    condition: Condition | None = None
    description: str = ""
    #: Instructions the PEP must carry out if this rule decides the request.
    obligations: tuple[str, ...] = ()
    #: Fields the caller must not receive even though the read is permitted.
    #: Field-level authorization: a warden may read a student record to confirm
    #: hall residence without seeing the disability disclosure on it.
    mask_fields: tuple[str, ...] = ()
    #: Fields the caller may write. Empty means "all fields the schema allows".
    writable_fields: tuple[str, ...] = ()
    #: Recorded on the decision. Set on rules whose every use is worth a look
    #: in the audit review, whether or not they granted.
    sensitive: bool = False

    def applies(self, **attrs: Any) -> bool:
        if self.condition is None:
            return True
        return self.condition.evaluate(**attrs)


@dataclass(frozen=True, slots=True)
class Policy:
    id: str
    description: str
    target: Target
    rules: tuple[Rule, ...]
    combining: Combining = Combining.DENY_OVERRIDES
    #: Lower runs first. Prohibitions live at low numbers so `FIRST_APPLICABLE`
    #: sets behave, and so the decision log reads in the order an auditor
    #: expects.
    priority: int = 100
    #: `False` parks a policy without deleting it. A parked policy still loads
    #: and still lints, so an institution can stage a rule change for the next
    #: intake and have CI check it.
    enabled: bool = True
    #: Where this came from: `builtin` (shipped), `tenant:<slug>` (overlay).
    source: str = "builtin"
    #: A policy set using PERMIT_OVERRIDES must name what it may override.
    overrides: tuple[str, ...] = ()
    version: int = 1

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, source: str = "builtin") -> Self:
        try:
            rules = tuple(_rule_from_dict(r, policy_id=data["id"]) for r in data.get("rules", ()))
        except KeyError as exc:
            raise ConditionError(f"policy is missing {exc}") from exc

        if not rules:
            raise ConditionError(f"policy {data.get('id')!r} declares no rules")

        target_data = data.get("target", {}) or {}
        combining = Combining(data.get("combining", Combining.DENY_OVERRIDES))
        overrides = tuple(data.get("overrides", ()))
        if combining is Combining.PERMIT_OVERRIDES and not overrides:
            raise ConditionError(
                f"policy {data['id']!r} uses permit_overrides but names nothing in "
                "`overrides`; an exception must say which prohibition it lifts"
            )

        return cls(
            id=data["id"],
            description=data.get("description", ""),
            target=Target(
                actions=frozenset(target_data.get("actions", ()) or ()),
                resource_types=frozenset(target_data.get("resource_types", ()) or ()),
                subject_kinds=frozenset(target_data.get("subject_kinds", ()) or ()),
                modules=frozenset(target_data.get("modules", ()) or ()),
            ),
            rules=rules,
            combining=combining,
            priority=int(data.get("priority", 100)),
            enabled=bool(data.get("enabled", True)),
            source=source,
            overrides=overrides,
            version=int(data.get("version", 1)),
        )


def _rule_from_dict(data: dict[str, Any], *, policy_id: str) -> Rule:
    rule_id = data.get("id") or f"{policy_id}#{data.get('effect', 'permit')}"
    raw_condition = data.get("condition")
    try:
        condition = compile_condition(raw_condition) if raw_condition else None
    except ConditionError as exc:
        raise ConditionError(f"{policy_id}/{rule_id}: {exc}") from exc
    return Rule(
        id=rule_id,
        effect=Effect(data.get("effect", "permit")),
        condition=condition,
        description=data.get("description", ""),
        obligations=tuple(data.get("obligations", ()) or ()),
        mask_fields=tuple(data.get("mask_fields", ()) or ()),
        writable_fields=tuple(data.get("writable_fields", ()) or ()),
        sensitive=bool(data.get("sensitive", False)),
    )
