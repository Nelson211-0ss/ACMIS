"""Checks on the shipped policy bundle itself.

The bundle is 54 policies and 137 rules of YAML, and its failure mode is not a
crash. A rule that reads a misspelt attribute, or an action no policy mentions
at all, produces a *silent* denial — which arrives as a support ticket saying
"the registrar can't see mark sheets" days later. Three such gaps were found by
hand during development; these tests exist so the fourth is found here.
"""

from __future__ import annotations

import ast
import re
from collections import defaultdict
from pathlib import Path

import pytest

from acmis.core.abac import resources
from acmis.core.abac.engine import PolicyEngine
from acmis.core.abac.expressions import referenced_attributes
from acmis.core.abac.policy import Effect
from acmis.modules import descriptors as _descriptors  # noqa: F401  (registers them)

API_ROOT = Path(__file__).resolve().parent.parent / "acmis"

#: Attribute names supplied by the engine itself for every request, so a rule
#: may read them on any resource type.
AMBIENT = frozenset({"id", "kind", "requested_by_id"})


def test_bundle_lints_clean(engine: PolicyEngine) -> None:
    assert engine.lint() == []


def test_every_targeted_resource_type_is_registered(engine: PolicyEngine) -> None:
    """A policy targeting an unregistered type can only ever see `{}`.

    Every attribute its rules read would be missing, so the policy is inert —
    and the YAML gives no hint of it.
    """
    known = set(resources.known_types())
    targeted = {t for p in engine.policies for t in (p.target.resource_types or ())}
    assert not targeted - known, (
        f"policies target unregistered resource types {sorted(targeted - known)}; "
        "no descriptor means no attributes, so their rules cannot match"
    )


def test_every_policy_has_rules(engine: PolicyEngine) -> None:
    empty = [p.id for p in engine.policies if not p.rules]
    assert not empty, f"policies with no rules never do anything: {empty}"


def test_rule_ids_read_as_sentences(engine: PolicyEngine) -> None:
    """Rule ids end up in denial messages and audit records, so they are read.

    Kebab-case throughout, because a mixture means nobody can guess the name of
    the rule they are looking for.
    """
    bad = [
        f"{p.id}/{r.id}"
        for p in engine.policies
        for r in p.rules
        if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", r.id)
    ]
    assert not bad, f"rule ids should be kebab-case: {bad}"


def test_deny_rules_explain_themselves(engine: PolicyEngine) -> None:
    """A deny a user can hit must say why.

    `explain_denials` returns the deciding rule's description to the caller, so
    a deny with no description shows a user "you do not have permission" and
    nothing else — the support call that follows is unanswerable.
    """
    silent = [
        f"{p.id}/{r.id}"
        for p in engine.policies
        for r in p.rules
        if r.effect is Effect.DENY and not (r.description or p.description)
    ]
    assert not silent, f"deny rules with no description: {silent}"


def test_rules_only_read_declared_resource_attributes(engine: PolicyEngine) -> None:
    """No rule reads an attribute none of its targeted types publishes.

    This is the misspelt-attribute check. A condition reading
    `resource.statuss` is not a syntax error — it evaluates to false, forever,
    and the rule simply never fires.

    A policy may target several types and hold a rule that only makes sense for
    one of them (`sit-open-assessment` reads `is_open`, which only an
    assessment has); that is idiomatic here, so the check is against the union
    of the targeted types' vocabularies.
    """
    published = resources.published_attributes()
    problems: list[str] = []
    for policy in engine.policies:
        types = policy.target.resource_types
        if not types:
            continue
        vocabulary = AMBIENT.union(*(published.get(t, frozenset()) for t in types))
        for rule in policy.rules:
            if rule.condition is None:
                continue
            read = {
                name.split(".", 1)[1]
                for name in referenced_attributes(rule.condition.source)
                if name.startswith("resource.")
            }
            for missing in sorted(read - vocabulary):
                problems.append(f"{policy.id}/{rule.id} reads resource.{missing}")
    assert not problems, (
        "rules read resource attributes no targeted type declares, so they can "
        f"never match: {problems}"
    )


# ---------------------------------------------------------------------------
# Every action the API takes must be reachable by some policy
# ---------------------------------------------------------------------------


def _enforced_actions() -> dict[str, set[str]]:
    """`{resource_type: {action, ...}}` for every enforcement point in the API.

    Read statically from the `authorize(...)` / `decide(...)` calls, because
    the list has to be exhaustive: the gap this catches is an action nobody
    wrote a policy for, which denies by default and is invisible until someone
    tries it.
    """
    found: dict[str, set[str]] = defaultdict(set)
    for path in sorted(API_ROOT.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Call):
                continue
            called = getattr(node.func, "id", getattr(node.func, "attr", ""))
            if called not in {"authorize", "decide"}:
                continue
            keywords = {k.arg: k.value for k in node.keywords if k.arg}
            action, resource_type = keywords.get("action"), keywords.get("resource_type")
            if isinstance(action, ast.Constant) and isinstance(resource_type, ast.Constant):
                found[str(resource_type.value)].add(str(action.value))
            elif isinstance(action, ast.JoinedStr) and isinstance(resource_type, ast.Constant):
                # f"mark_sheet:{action}" — the verb comes from the URL, so
                # every verb the endpoint accepts is covered by the prefix.
                prefix = next(
                    (
                        v.value
                        for v in action.values
                        if isinstance(v, ast.Constant) and isinstance(v.value, str)
                    ),
                    None,
                )
                if prefix:
                    found[str(resource_type.value)].add(f"{prefix}*")
    return dict(found)


def _actions_named_by(condition: str) -> tuple[set[str], list[str]]:
    """Literal actions and `matches(action, ...)` patterns named in a condition."""
    literals: set[str] = set()
    patterns: list[str] = []
    tree = ast.parse(condition.strip(), mode="eval")
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "matches"
            and len(node.args) == 2
            and isinstance(node.args[0], ast.Attribute | ast.Name)
            and isinstance(node.args[1], ast.Constant)
        ):
            patterns.append(str(node.args[1].value))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and ":" in node.value:
            literals.add(node.value)
    return literals, patterns


ENFORCED = _enforced_actions()


@pytest.mark.parametrize("resource_type", sorted(ENFORCED))
def test_every_enforced_action_is_named_by_a_policy(
    resource_type: str, engine: PolicyEngine
) -> None:
    """Some policy mentions each action the API enforces.

    Not "permits" — that depends on who is asking. Merely *mentions*: an action
    no policy names anywhere is denied by default for everyone, which is a
    feature nobody can use. Two of those shipped during development
    (`oneroster:*` and `question:import`).
    """
    named: set[str] = set()
    patterns: list[str] = []
    for policy in engine.policies:
        types = policy.target.resource_types
        if types and resource_type not in types:
            continue
        named |= set(policy.target.actions or ())
        for rule in policy.rules:
            if rule.condition is None:
                continue
            literals, rule_patterns = _actions_named_by(rule.condition.source)
            named |= literals
            patterns += rule_patterns

    unreachable: list[str] = []
    for action in sorted(ENFORCED[resource_type]):
        if action.endswith("*"):
            prefix = action[:-1]
            if any(n.startswith(prefix) for n in named) or any(
                p.startswith(prefix.split(":")[0]) or prefix.split(":")[0] in p for p in patterns
            ):
                continue
        elif action in named or any(re.fullmatch(p, action) for p in patterns):
            continue
        unreachable.append(action)

    assert not unreachable, (
        f"no policy targeting {resource_type!r} names {unreachable} — those actions "
        "are denied by default for every caller"
    )
