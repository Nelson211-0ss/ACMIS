"""A small, safe expression language for policy conditions.

Policy conditions are written as Python-looking expressions:

    subject.kind == "staff"
    and "results:enter" in subject.permissions
    and resource.department_id in subject.department_ids
    and resource.status in ["draft", "returned"]
    and not resource.is_locked

Why a restricted evaluator instead of `eval`, and instead of pulling in OPA or
Casbin?

`eval` is out on its face: a policy bundle is data — it is loaded from disk and
from the tenant database, and a tenant administrator can add overlay rules. An
unrestricted `eval` there turns "the registrar edited an authorization rule"
into remote code execution inside the process that holds every university's
database credentials.

OPA/Rego and Cedar are both better languages than this one. They were rejected
for a specific reason: an authorization decision here happens several times per
request and sits in front of every query, and both engines put either a network
hop or a foreign runtime between the request and its answer. Cedar has no
first-party Python binding; OPA means running and versioning a sidecar per
deployment and shipping the whole attribute set over the wire to ask about one
record. This evaluator compiles each condition once at load time into a Python
code object and evaluates it against plain dicts, so a decision is tens of
microseconds and cannot fail because a sidecar is restarting. The trade is that
this language is far less expressive — deliberately: no loops, no assignment,
no imports, no attribute access into arbitrary objects. If a rule cannot be
said in these terms, it does not belong in a policy, it belongs in the module's
own rule engine where it can be tested.

What is allowed: boolean operators, comparisons, membership, arithmetic on
numbers, indexing, list/tuple/set/dict literals, conditional expressions, and
calls to the whitelisted helpers in `SAFE_FUNCTIONS`. Everything else — `Call`
to anything unlisted, `Attribute` on anything but a known root, comprehensions,
lambdas, walrus, f-strings, `import`, dunder access — is rejected at *load*
time, so a malformed policy fails when the bundle is loaded, not on the first
request that happens to touch it.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime
from typing import Any

__all__ = ["SAFE_FUNCTIONS", "Condition", "ConditionError", "compile_condition"]


class ConditionError(ValueError):
    """A condition that cannot be compiled. Always a policy-authoring bug."""


# ---------------------------------------------------------------------------
# Helper functions available inside conditions
# ---------------------------------------------------------------------------


def _any_in(candidates: Any, collection: Any) -> bool:
    """True if any element of `candidates` appears in `collection`.

    The workhorse of unit-scoped rules: a dean attached to three faculties may
    act on a record belonging to any one of them.
    """
    if candidates is None or collection is None:
        return False
    if isinstance(candidates, (str, bytes)):
        candidates = [candidates]
    if isinstance(collection, (str, bytes)):
        collection = [collection]
    try:
        haystack = set(collection)
    except TypeError:
        return False
    return any(c in haystack for c in candidates)


def _all_in(candidates: Any, collection: Any) -> bool:
    if candidates is None or collection is None:
        return False
    if isinstance(candidates, (str, bytes)):
        candidates = [candidates]
    if isinstance(collection, (str, bytes)):
        collection = [collection]
    try:
        haystack = set(collection)
    except TypeError:
        return False
    return all(c in haystack for c in candidates)


def _matches(value: Any, pattern: str) -> bool:
    """Anchored regex match. Used for code shapes like `^BSC-[0-9]{3}$`."""
    if value is None:
        return False
    return re.fullmatch(pattern, str(value)) is not None


def _days_between(a: Any, b: Any) -> float:
    """Signed day difference, for deadline rules ("within 21 days of release")."""
    left, right = _as_datetime(a), _as_datetime(b)
    if left is None or right is None:
        return float("nan")
    return (left - right).total_seconds() / 86400.0


def _as_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def _now() -> datetime:
    return datetime.now(UTC)


def _length(value: Any) -> int:
    try:
        return len(value)
    except TypeError:
        return 0


def _has(mapping: Any, key: Any) -> bool:
    """`has(resource, "grade")` — distinguishes absent from present-and-null.

    A policy that says "an examiner may edit a mark that has no grade yet"
    means absent, and `resource.grade == None` cannot tell the two apart when a
    caller simply did not load the column.
    """
    if isinstance(mapping, Mapping):
        return key in mapping
    return hasattr(mapping, str(key))


#: The complete set of callables reachable from a condition.
def _owns(resource_value: Any, subject_value: Any) -> bool:
    """True when the resource *belongs to* the subject.

    Exists because `resource.student_id == subject.student_id` is wrong, and
    wrong in the dangerous direction. Two ways:

    1. **Both absent.** A class-level decision — "may this actor list student
       records at all?" — carries no `student_id`, and a subject who is not a
       student has none either. `None == None` is `True`, so an "own record"
       rule *grants the whole class* to anyone. That is not hypothetical: it
       shipped, and a member of staff could list the library's entire
       circulation register through a rule meant to show readers their own
       loans.

    2. **Both genuinely null.** A library fine raised against a member of
       staff has `student_id IS NULL`; a lecturer's own `student_id` is null
       too. The same comparison makes every staff fine look like the
       lecturer's own.

    So ownership requires two things present and equal. Compared as text
    because the resource side arrives normalised to strings by the descriptor
    layer while the subject side may still be a `UUID`.
    """
    if resource_value is None or subject_value is None:
        return False
    if isinstance(resource_value, bool) or isinstance(subject_value, bool):
        # Guard against `owns(True, True)`, which is never a meaningful
        # ownership question and would otherwise quietly succeed.
        return False
    return str(resource_value) == str(subject_value)


SAFE_FUNCTIONS: dict[str, Any] = {
    "any_in": _any_in,
    "all_in": _all_in,
    "matches": _matches,
    "days_between": _days_between,
    "now": _now,
    "len": _length,
    "has": _has,
    "owns": _owns,
    "abs": abs,
    "min": min,
    "max": max,
    "round": round,
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "sorted": sorted,
    "sum": sum,
}

#: Names a condition may resolve. Anything else is a load-time error, which
#: turns the classic typo — `subjects.roles` — into a failed deploy instead of
#: a rule that silently never matches and quietly denies everyone.
ALLOWED_ROOTS = frozenset(
    {"subject", "resource", "action", "environment", "tenant", "context", *SAFE_FUNCTIONS}
)

_ALLOWED_NODES: tuple[type[ast.AST], ...] = (
    ast.Expression,
    ast.BoolOp,
    ast.And,
    ast.Or,
    ast.UnaryOp,
    ast.Not,
    ast.USub,
    ast.UAdd,
    ast.BinOp,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Compare,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.In,
    ast.NotIn,
    ast.Is,
    ast.IsNot,
    ast.Call,
    ast.Name,
    ast.Load,
    ast.Constant,
    ast.Attribute,
    ast.Subscript,
    ast.List,
    ast.Tuple,
    ast.Set,
    ast.Dict,
    ast.IfExp,
    ast.Slice,
)


class _Validator(ast.NodeVisitor):
    """Rejects anything outside the language before the condition is compiled."""

    def __init__(self) -> None:
        self.roots: set[str] = set()

    def generic_visit(self, node: ast.AST) -> None:
        if not isinstance(node, _ALLOWED_NODES):
            raise ConditionError(f"`{type(node).__name__}` is not allowed in a policy condition")
        super().generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr.startswith("_"):
            raise ConditionError(f"attribute `{node.attr}` is not readable from a policy")
        # Only `root.field` and `root.field.field` — never an attribute walk
        # onto an arbitrary object graph.
        base = node.value
        # Both `Attribute` and `Subscript` expose `.value`, so one walk covers
        # `resource.a.b` and `resource.a["b"]` alike.
        while isinstance(base, (ast.Attribute, ast.Subscript)):
            base = base.value
        if not isinstance(base, ast.Name):
            raise ConditionError("attribute access must start from a named root")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if not isinstance(node.func, ast.Name):
            raise ConditionError("only the built-in policy helpers may be called")
        if node.func.id not in SAFE_FUNCTIONS:
            raise ConditionError(
                f"`{node.func.id}()` is not a policy helper; "
                f"available: {', '.join(sorted(SAFE_FUNCTIONS))}"
            )
        if node.keywords:
            raise ConditionError("policy helpers take positional arguments only")
        for arg in node.args:
            self.visit(arg)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id not in ALLOWED_ROOTS:
            raise ConditionError(
                f"unknown name `{node.id}` in condition; "
                f"roots are subject, resource, action, environment, tenant, context"
            )
        self.roots.add(node.id)


class _Attrs(dict[str, Any]):
    """Dict that also answers attribute access, and answers `None` when absent.

    Conditions read `resource.department_id`, but the attribute set arrives as
    a plain dict — from a Pydantic model, a SQLAlchemy row, or hand-built in a
    test. Missing keys yield `None` rather than raising, so a rule stays
    evaluable against a partially-loaded resource; combined with the
    deny-by-default combining rule, an attribute nobody supplied can only ever
    make a `permit` fail to match. It can never grant.
    """

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        value = self.get(name)
        if isinstance(value, Mapping):
            return _Attrs(value)
        return value

    def __missing__(self, key: str) -> Any:
        return None


def wrap(value: Mapping[str, Any] | None) -> _Attrs:
    return _Attrs(value or {})


class Condition:
    """A compiled policy condition.

    Compiled once when the bundle loads. Evaluation is a plain `eval` of a code
    object whose globals contain nothing but the helpers — `__builtins__` is
    explicitly emptied, without which `().__class__.__bases__` walks out to
    `object` and from there to anything importable.
    """

    __slots__ = ("_code", "roots", "source")

    def __init__(self, source: str, code: Any, roots: frozenset[str]) -> None:
        self.source = source
        self._code = code
        self.roots = roots

    def evaluate(
        self,
        *,
        subject: Mapping[str, Any],
        resource: Mapping[str, Any],
        action: str,
        environment: Mapping[str, Any] | None = None,
        tenant: Mapping[str, Any] | None = None,
        context: Mapping[str, Any] | None = None,
    ) -> bool:
        """Evaluate as a predicate. A policy condition is always a boolean."""
        return bool(
            self.evaluate_value(
                subject=subject,
                resource=resource,
                action=action,
                environment=environment,
                tenant=tenant,
                context=context,
            )
        )

    def evaluate_value(
        self,
        *,
        subject: Mapping[str, Any] | None = None,
        resource: Mapping[str, Any] | None = None,
        action: str = "",
        environment: Mapping[str, Any] | None = None,
        tenant: Mapping[str, Any] | None = None,
        context: Mapping[str, Any] | None = None,
    ) -> Any:
        """Evaluate and return the raw result, uncoerced.

        `evaluate` wraps this in `bool()` because a policy condition is a
        predicate. Other callers need the value itself: a calculated question's
        answer formula is the same restricted expression language evaluating to
        a number, and coercing that to a boolean turns every answer into True.
        """
        scope = {
            "__builtins__": {},
            **SAFE_FUNCTIONS,
            "subject": wrap(subject),
            "resource": wrap(resource),
            "action": action,
            "environment": wrap(environment),
            "tenant": wrap(tenant),
            "context": wrap(context),
        }
        try:
            return eval(self._code, scope, {})  # noqa: S307 - AST-validated at load
        except Exception as exc:  # a rule that errors must not grant access
            raise ConditionError(f"expression failed at runtime: {self.source!r}: {exc}") from exc

    def __repr__(self) -> str:  # pragma: no cover
        return f"Condition({self.source!r})"


def compile_condition(source: str) -> Condition:
    """Parse, validate and compile a condition. Raises `ConditionError`.

    Whitespace is collapsed first. A condition is one expression, and policy
    authors break it across lines for readability — but YAML's folded scalars
    preserve a newline before a more-indented line, which turns a readable
    multi-line condition into `...] \n and ...` and a syntax error. Collapsing
    means the YAML block style an author happens to pick has no bearing on
    whether their policy loads.
    """
    text = " ".join(source.split())
    if not text:
        raise ConditionError("condition is empty; omit it instead of leaving it blank")
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise ConditionError(f"cannot parse condition {text!r}: {exc.msg}") from exc

    validator = _Validator()
    validator.visit(tree)
    code = compile(tree, filename="<acmis-policy>", mode="eval")
    return Condition(text, code, frozenset(validator.roots))


def referenced_attributes(source: str) -> set[str]:
    """`{"subject.roles", "resource.status"}` — used by the policy linter.

    Lets the test suite assert that no policy reads an attribute the resource
    descriptor never populates, which is the failure mode that produces a rule
    that looks correct and never fires.
    """
    tree = ast.parse(source.strip(), mode="eval")
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            found.add(f"{node.value.id}.{node.attr}")
    return found


def as_iterable(value: Any) -> Iterable[Any]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        return (value,)
    if isinstance(value, Iterable):
        return value
    return (value,)
