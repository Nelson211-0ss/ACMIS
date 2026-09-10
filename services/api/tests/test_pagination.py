"""Cursor encoding, which every list endpoint depends on.

A cursor is opaque to clients but it still has to round-trip exactly, including
the awkward case: a null sort key. A cursor that cannot point inside the null
block makes the last page of a nullable-sorted list repeat forever.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from acmis.core.pagination import _decode_key, _encode_key
from acmis.core.schemas import Cursor, Page, PageParams


def test_cursor_round_trips() -> None:
    identifier = uuid.uuid4()
    cursor = Cursor(key="Namubiru Grace", id=identifier)
    restored = Cursor.decode(cursor.encode())
    assert restored is not None
    assert (restored.key, restored.id) == ("Namubiru Grace", identifier)


def test_cursor_survives_a_null_sort_key() -> None:
    """`key=None` means "inside the block of rows whose sort key is null"."""
    cursor = Cursor(key=None, id=uuid.uuid4())
    restored = Cursor.decode(cursor.encode())
    assert restored is not None
    assert restored.key is None


def test_cursor_is_url_safe_and_unpadded() -> None:
    encoded = Cursor(key="a/b+c=d", id=uuid.uuid4()).encode()
    assert "=" not in encoded and "/" not in encoded and "+" not in encoded


@pytest.mark.parametrize("value", ["", "not-base64!", "AAAA", "eyJrIjoxfQ"])
def test_a_broken_cursor_gives_the_first_page(value: str) -> None:
    """A stale bookmark is answered with page one, not with a 400.

    The usual cause is a client that kept a cursor across a deploy, and an
    error page is a worse answer than the first page.
    """
    assert Cursor.decode(value) is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("Okello", "Okello"),
        (42, "42"),
        (Decimal("72.50"), "72.50"),
        (True, "true"),
        (False, "false"),
        (date(2026, 9, 9), "2026-09-09"),
        (datetime(2026, 9, 9, 8, 30, tzinfo=UTC), "2026-09-09T08:30:00+00:00"),
    ],
)
def test_sort_keys_encode_losslessly(value: object, expected: str | None) -> None:
    assert _encode_key(value) == expected


def test_a_key_of_the_wrong_shape_is_dropped_rather_than_raising() -> None:
    """A cursor from before a sort key changed type must not 500."""
    from sqlalchemy import Integer, literal_column

    column = literal_column("n", Integer)
    assert _decode_key(column, "not-a-number") is None
    assert _decode_key(column, "17") is not None


def test_page_meta_says_whether_more_exists() -> None:
    empty: Page[str] = Page.of([], limit=20)
    assert empty.meta.has_more is False and empty.meta.next_cursor is None

    more: Page[str] = Page.of(["a"], limit=1, next_cursor="abc", total=9)
    assert more.meta.has_more is True and more.meta.total == 9


def test_page_params_bound_the_limit() -> None:
    with pytest.raises(ValueError):
        PageParams(limit=0)
    with pytest.raises(ValueError):
        PageParams(limit=1000)
    assert PageParams().limit == 50
