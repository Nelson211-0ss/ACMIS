"""SQL shapes that are wrong *silently*, checked so they stay fixed.

Every test here corresponds to a query that compiled, ran, returned no error,
and gave the wrong answer. That is the expensive kind of bug in this system: a
scoping rule that never matches reads exactly like a rule that decided not to
apply, and nobody investigates a decision that looks deliberate.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, cast

import pytest
from sqlalchemy import Integer, column, literal, select
from sqlalchemy.dialects import postgresql

API_ROOT = Path(__file__).resolve().parent.parent / "acmis"


def test_nothing_is_ever_in_a_null() -> None:
    """The premise: `x IN (1, NULL)` does not match a NULL `x`.

    This is standard three-valued logic and it is the reason
    `col.in_((value, None))` is a bug rather than a shortcut. Pinned as a test
    because the shortcut reads so plausibly — "either this programme or the
    one with no programme" — and it silently matches neither.
    """
    scope = column("programme_id", Integer)
    # SQLAlchemy's dialect factory carries no annotations, and mypy is strict
    # here; the cast keeps that one call out of the way without loosening the
    # settings for the whole suite.
    dialect = cast("Any", postgresql.dialect)()
    compiled = (
        select(literal(1))
        .where(scope.in_((7, None)))
        .compile(dialect=dialect, compile_kwargs={"literal_binds": True})
    )
    sql = str(compiled)
    # SQLAlchemy emits the NULL faithfully; it is Postgres that will never
    # match it. The assertion is that the *shape* is what we think it is.
    assert "IN (7, NULL)" in sql.replace("\n", " ")


def _optional_scope_offenders() -> list[str]:
    """`x.in_((something, None))` anywhere in the codebase.

    The literal `None` inside an `in_` is what makes this findable: an `in_`
    over a computed tuple is not necessarily wrong, and is not flagged.
    """
    offenders: list[str] = []
    for path in sorted(API_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not (isinstance(node.func, ast.Attribute) and node.func.attr == "in_"):
                continue
            for argument in node.args:
                if not isinstance(argument, ast.Tuple | ast.List):
                    continue
                if any(
                    isinstance(element, ast.Constant) and element.value is None
                    for element in argument.elts
                ):
                    offenders.append(
                        f"{path.relative_to(API_ROOT)}:{node.lineno} {ast.unparse(node)[:80]}"
                    )
    return offenders


def test_no_optional_scope_written_as_in_null() -> None:
    """An optional scope has to be `or_(col == value, col.is_(None))`.

    Written as `col.in_((value, None))` it compiles, runs, and never matches
    the fallback row. This shipped twice: the institution-wide late-payment
    rule and the institution-wide library loan policy were both unreachable,
    which made every invoice come back "no rule applies" and would have made
    a branch with no policy of its own refuse every issue.
    """
    offenders = _optional_scope_offenders()
    assert not offenders, (
        "these use `IN (..., NULL)`, which matches no NULL row — use "
        "`or_(col == value, col.is_(None))` instead:\n  " + "\n  ".join(offenders)
    )


@pytest.mark.parametrize(
    "module",
    ["acmis.modules.finance.latepayment", "acmis.modules.library.service"],
)
def test_the_two_fixed_lookups_use_is_null(module: str) -> None:
    """And specifically: the two that were wrong now say `is_(None)`."""
    source = Path(API_ROOT.parent / (module.replace(".", "/") + ".py")).read_text()
    assert ".is_(None)" in source
    assert "or_(" in source


def _unordered_limits() -> list[str]:
    """`.limit(n)` with no `.order_by()` in the same chain."""

    def chain_has(node: ast.AST, attribute: str) -> bool:
        while isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == attribute:
                return True
            node = node.func.value
        return False

    offenders: list[str] = []
    for path in sorted(API_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            if node.func.attr != "limit" or chain_has(node, "order_by"):
                continue
            offenders.append(f"{path.relative_to(API_ROOT)}:{node.lineno}")
    return offenders


def test_no_limit_without_an_order_by() -> None:
    """An unordered `LIMIT` returns whichever rows the planner reaches first.

    Not a style point. In the seeder it meant two runs acted on different
    invoices, so nothing was reproducible; in a paged endpoint it means the
    same page returns different rows on each request, which is the bug keyset
    pagination exists to prevent — and `keyset_page` always orders, which is
    why the endpoints are clean.
    """
    offenders = _unordered_limits()
    assert not offenders, (
        "these take a LIMIT without an ORDER BY, so the rows returned are "
        f"whatever the planner reaches first: {offenders}"
    )


def test_money_is_held_in_64_bit_columns() -> None:
    """Every `*_minor` column is a `BigInteger`.

    Money is stored in minor units, so a 32-bit column caps a single value at
    2,147,483,647 — about 21.4 million UGX, or roughly five semesters of one
    student's fees. A student's lifetime `total_paid_minor` therefore
    overflows part way through a degree, and an institution-level ledger
    account overflows at once. It surfaced as
    `NumericValueOutOfRange` on a legitimate recompute.

    Deliberately not applied to counts: `days_overdue`, `instalment_count`,
    `concurrent_users` and the like stay 32-bit, because that range is honest
    about what they hold.
    """
    from sqlalchemy import BigInteger

    from acmis.core.models import TenantBase
    from acmis.modules.registry import configure

    configure()
    wrong: list[str] = []
    for table in TenantBase.metadata.tables.values():
        for money in table.columns:
            if not money.name.endswith("_minor"):
                continue
            if not isinstance(money.type, BigInteger):
                wrong.append(f"{table.name}.{money.name}: {money.type}")
    assert not wrong, (
        f"money columns must be BigInteger; 32 bits caps a value at about 21 million UGX: {wrong}"
    )
