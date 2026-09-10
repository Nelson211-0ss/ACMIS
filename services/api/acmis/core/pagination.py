"""Keyset pagination for every list endpoint.

Offset pagination fails on exactly the tables that most need paging. A list of
applications ordered by score shifts while an admissions officer works down it:
one more application is scored, every row moves, and page two skips a candidate
page one never showed. That is a wrong decision caused by a pagination
strategy, and no amount of care by the officer can detect it.

Keyset pagination anchors instead on the last row handed out. The predicate
here is generated from the *same* key expression as the ORDER BY, which is what
makes the two agree — a keyset filter that does not exactly mirror the ordering
silently drops or repeats rows, which is worse than offset paging because it
looks correct.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import Select, and_, func, literal, or_, select
from sqlalchemy.orm import InstrumentedAttribute, Session
from sqlalchemy.sql.elements import ColumnElement

from acmis.core.schemas import Cursor, PageParams

NullsPlacement = Literal["first", "last"]

#: A mapped column or any expression over the row. Both forms carry the
#: operators and the `.type` this module needs; mypy does not consider a mapped
#: attribute a `ColumnElement`, so both are named.
type SortKey = InstrumentedAttribute[Any] | ColumnElement[Any]


def _encode_key(value: Any) -> str | None:
    """Render a sort key as the cursor's opaque text form."""
    if value is None:
        return None
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _decode_key(expr: SortKey, raw: str) -> ColumnElement[Any] | None:
    """Turn cursor text back into a bind parameter of the key's own type.

    Bound with `expr.type` rather than left to inference: comparing a text
    literal against a numeric column makes Postgres cast the *column*, which
    loses the index the ordering depends on.
    """
    try:
        python_type: type[Any] = expr.type.python_type
    except NotImplementedError:  # pragma: no cover - an untyped expression
        python_type = str
    try:
        value: Any
        if python_type is datetime:
            value = datetime.fromisoformat(raw)
        elif python_type is date:
            value = date.fromisoformat(raw)
        elif python_type is uuid.UUID:
            value = uuid.UUID(raw)
        elif python_type is bool:
            value = raw == "true"
        elif python_type is int:
            value = int(raw)
        elif python_type is float:
            value = float(raw)
        elif python_type is Decimal:
            value = Decimal(raw)
        else:
            value = raw
    except (ValueError, ArithmeticError):
        # A stale bookmark from before a sort key changed type. The first page
        # is a better answer than an error, exactly as in `Cursor.decode`.
        return None
    return literal(value, expr.type)


@dataclass(slots=True)
class Paged[M]:
    """Rows for one page, plus what the envelope needs."""

    rows: list[M]
    next_cursor: str | None = None
    total: int | None = None


def keyset_page[M](
    db: Session,
    stmt: Select[tuple[M]],
    *,
    page: PageParams,
    key: SortKey,
    ident: SortKey,
    descending: bool = False,
    nulls: NullsPlacement | None = None,
) -> Paged[M]:
    """Run `stmt` as one keyset page.

    `key` is the sort column (or any deterministic expression over the row) and
    `ident` the unique tiebreak — without a tiebreak, rows sharing a key can be
    returned in a different order on each request and the cursor then lands
    mid-cluster. `nulls` defaults to Postgres' own default for the direction,
    so passing nothing reproduces a bare `ORDER BY key` / `ORDER BY key DESC`.
    """
    nulls_first = (nulls == "first") if nulls is not None else descending

    total: int | None = None
    if page.with_total:
        # Counted before the cursor filter: a total that shrinks as the reader
        # pages through it is not a total.
        total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()

    cursor = Cursor.decode(page.cursor)
    if cursor is not None:
        after_ident = ident > literal(cursor.id)
        if cursor.key is None:
            # The anchor sits in the null block.
            in_null_block = and_(key.is_(None), after_ident)
            stmt = stmt.where(
                or_(in_null_block, key.is_not(None)) if nulls_first else in_null_block
            )
        else:
            anchor = _decode_key(key, cursor.key)
            if anchor is not None:
                stepped = key < anchor if descending else key > anchor
                clauses = [stepped, and_(key == anchor, after_ident)]
                if not nulls_first:
                    # Nulls come after every real key, so they are still ahead.
                    clauses.append(key.is_(None))
                stmt = stmt.where(or_(*clauses))

    ordering = key.desc() if descending else key.asc()
    ordering = ordering.nullsfirst() if nulls_first else ordering.nullslast()

    result = db.execute(
        stmt.add_columns(key, ident).order_by(ordering, ident.asc()).limit(page.limit + 1)
    ).all()

    has_more = len(result) > page.limit
    window = result[: page.limit]
    next_cursor: str | None = None
    if has_more and window:
        last = window[-1]
        next_cursor = Cursor(key=_encode_key(last[-2]), id=last[-1]).encode()
    return Paged(rows=[row[0] for row in window], next_cursor=next_cursor, total=total)
