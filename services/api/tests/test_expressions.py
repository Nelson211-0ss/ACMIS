"""The condition language.

Policy conditions are Python expressions evaluated at request time, which is
only acceptable because the compiler refuses everything that is not an
expression over the request. These tests are the specification of that refusal:
if one of them starts passing where it should fail, a policy author — or
anything that can write a policy overlay — has arbitrary code execution inside
the authorization path.
"""

from __future__ import annotations

import pytest

from acmis.core.abac.expressions import (
    Condition,
    compile_condition,
    referenced_attributes,
)

# Each of these is a real escape attempt against an AST allow-list.
FORBIDDEN = [
    "__import__('os').system('id')",
    "().__class__.__base__.__subclasses__()",
    "open('/etc/passwd').read()",
    "eval('1+1')",
    "exec('x=1')",
    "globals()",
    "locals()",
    "subject.__class__",
    "[x for x in ()]",
    "lambda: 1",
    "subject.permissions := []",
    "getattr(subject, 'permissions')",
    "type(subject)",
    "compile('1', '<s>', 'eval')",
    "vars(subject)",
]


@pytest.mark.parametrize("source", FORBIDDEN)
def test_unsafe_expressions_are_refused(source: str) -> None:
    with pytest.raises(Exception):  # noqa: B017 - any refusal is a pass here
        compile_condition(source)


def test_statements_are_refused() -> None:
    for source in ("x = 1", "if True: pass", "import os"):
        with pytest.raises(Exception):  # noqa: B017
            compile_condition(source)


def test_folded_yaml_whitespace_does_not_change_meaning() -> None:
    """YAML block scalars fold long conditions across lines.

    The compiler collapses whitespace so that a condition an author wrapped for
    readability is the same condition as the one-line form. Without this, a
    rule changes behaviour when someone reformats the YAML.
    """
    folded = compile_condition(
        '"results:enter" in subject.permissions\n  and action == "mark_sheet:read"\n'
    )
    inline = compile_condition(
        '"results:enter" in subject.permissions and action == "mark_sheet:read"'
    )
    assert folded.source == inline.source


def _evaluate(
    source: str,
    *,
    subject: dict[str, object] | None = None,
    resource: dict[str, object] | None = None,
    action: str = "",
    **extra: dict[str, object],
) -> bool:
    return compile_condition(source).evaluate(
        subject=subject or {}, resource=resource or {}, action=action, **extra
    )


def test_missing_attributes_are_false_not_errors() -> None:
    """An attribute the resource does not publish makes the rule not match.

    Deliberate: a rule that reads `resource.is_open` on a resource type with no
    such attribute must not match, and must not 500 either — a policy bundle
    that can crash a request is worse than one that over-denies.
    """
    assert _evaluate("resource.is_open == True", resource={}) is False
    assert _evaluate('resource.status == "open"', resource={}) is False


def test_none_is_not_equal_to_none_by_accident() -> None:
    """The `None == None` trap, which shipped once and refused every marker.

    `no-marking-own-attempt` compared `resource.student_id` with
    `subject.student_id`. For a member of staff marking a candidate's script
    both were `None`, the deny matched, and no essay could be marked by anyone.
    The rules now guard on `!= None` explicitly; this test pins the semantics
    they rely on.
    """
    assert _evaluate("resource.student_id == subject.student_id", resource={}, subject={}) is True
    assert (
        _evaluate(
            "resource.student_id != None and resource.student_id == subject.student_id",
            resource={},
            subject={},
        )
        is False
    )


def test_evaluate_value_returns_the_value_not_a_truthiness() -> None:
    """Calculated questions evaluate a formula through the same compiler.

    `evaluate` coerces to bool for policy use. A question whose answer is
    computed needs the number, and using `evaluate` for it once made every
    calculated answer come out as `True`.
    """
    condition: Condition = compile_condition("context.a * 2 + context.b")
    values = {"a": 3, "b": 1}
    assert condition.evaluate_value(context=values) == 7
    assert condition.evaluate(subject={}, resource={}, action="", context=values) is True


def test_matches_is_anchored() -> None:
    """`matches` is a full match, not a search.

    A rule reading `matches(action, "mark_sheet:read")` must not also permit
    `mark_sheet:read_sensitive`.
    """
    assert _evaluate('matches(action, "mark_sheet:(read|list)")', action="mark_sheet:read") is True
    assert (
        _evaluate('matches(action, "mark_sheet:(read|list)")', action="mark_sheet:read_sensitive")
        is False
    )


def test_referenced_attributes_finds_both_sides() -> None:
    found = referenced_attributes('resource.status == "open" and subject.staff_id != None')
    assert found == {"resource.status", "subject.staff_id"}
