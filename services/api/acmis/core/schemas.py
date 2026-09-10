"""Shared response shapes.

Every list endpoint in ACMIS returns `Page[T]` and every error returns
`ErrorEnvelope`. Nine frontend apps consume this API; a list endpoint that
invents its own pagination shape means one more special case in the generated
client and one more thing that breaks differently.
"""

from __future__ import annotations

import base64
import binascii
import json
import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Schema(BaseModel):
    """Base for every request/response model."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        str_strip_whitespace=True,
        extra="forbid",
        use_enum_values=True,
        ser_json_timedelta="iso8601",
    )


class ErrorPayload(Schema):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorEnvelope(Schema):
    error: ErrorPayload


class PageMeta(Schema):
    """Keyset pagination.

    Cursors, not offsets. `LIMIT 50 OFFSET 20000` on a 400,000-row mark table
    makes Postgres walk 20,050 rows to return 50, and it skips or repeats rows
    when the underlying set changes between pages — which it does constantly
    during a results-entry window. `total` is therefore optional and only
    computed when a caller asks for it.
    """

    limit: int
    next_cursor: str | None = None
    previous_cursor: str | None = None
    total: int | None = None
    has_more: bool = False


class Page[T](Schema):
    items: list[T]
    meta: PageMeta

    @classmethod
    def of(
        cls,
        items: list[T],
        *,
        limit: int,
        next_cursor: str | None = None,
        previous_cursor: str | None = None,
        total: int | None = None,
    ) -> Self:
        return cls(
            items=items,
            meta=PageMeta(
                limit=limit,
                next_cursor=next_cursor,
                previous_cursor=previous_cursor,
                total=total,
                has_more=next_cursor is not None,
            ),
        )


class Cursor(Schema):
    """An opaque, base64 keyset cursor.

    Opaque because it is a private contract: encoding the sort key in the clear
    invites clients to construct one, and then the sort key can never change.
    Not signed — a tampered cursor can only produce a differently-ordered page
    of records the caller was already authorised to read, and every row still
    passes the same authorization check.
    """

    #: `None` means "the block of rows whose sort key is null" — a nullable
    #: sort key needs a cursor that can point inside it.
    key: str | None
    id: uuid.UUID

    def encode(self) -> str:
        raw = json.dumps({"k": self.key, "i": str(self.id)}, separators=(",", ":"))
        return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")

    @classmethod
    def decode(cls, value: str | None) -> Self | None:
        if not value:
            return None
        try:
            padded = value + "=" * (-len(value) % 4)
            data = json.loads(base64.urlsafe_b64decode(padded))
            raw_key = data["k"]
            return cls(
                key=None if raw_key is None else str(raw_key),
                id=uuid.UUID(str(data["i"])),
            )
        except (ValueError, KeyError, binascii.Error, json.JSONDecodeError):
            # A malformed cursor returns the first page rather than a 400. The
            # usual cause is a stale bookmark, and an error page is a worse
            # answer than the first page.
            return None


class PageParams(Schema):
    limit: Annotated[int, Field(ge=1, le=200)] = 50
    cursor: str | None = None
    #: Costs a `COUNT(*)`; off unless the UI is actually showing "of 1,240".
    with_total: bool = False

    @property
    def decoded_cursor(self) -> Cursor | None:
        return Cursor.decode(self.cursor)


class SortParams(Schema):
    sort_by: str | None = None
    sort_dir: Literal["asc", "desc"] = "asc"


class Money(Schema):
    """Money as integer minor units plus an ISO currency.

    Never a float. `0.1 + 0.2 != 0.3` in binary floating point, and a fee
    ledger that drifts by a fraction of a shilling per transaction reconciles
    to nothing at the end of a semester. Minor units also sidestep the
    zero-decimal question: UGX has no subunit in practice, KES and SSP do, and
    `amount_minor` with an explicit `currency` is correct for all three.
    """

    amount_minor: int
    currency: str = "UGX"

    @field_validator("currency")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()

    @property
    def major(self) -> float:
        return self.amount_minor / 100

    def __add__(self, other: Money) -> Money:
        if other.currency != self.currency:
            raise ValueError("cannot add different currencies")
        return Money(amount_minor=self.amount_minor + other.amount_minor, currency=self.currency)


class AuditStamp(Schema):
    created_at: datetime
    updated_at: datetime
    created_by_id: uuid.UUID | None = None
    updated_by_id: uuid.UUID | None = None
    version: int = 1


class Capability(Schema):
    """What the signed-in actor may do with a record.

    Returned alongside the record so the UI does not have to guess, and does
    not have to re-implement the policy bundle in TypeScript to decide whether
    to render an Approve button. The server already knows; this is it saying so.
    """

    action: str
    allowed: bool
    reason: str | None = None


class RecordEnvelope[T](Schema):
    data: T
    capabilities: list[Capability] = Field(default_factory=list)
    #: Fields withheld from `data` by the field-level mask, named so the UI can
    #: render "restricted" rather than an empty cell that looks like missing
    #: data. Naming *that a field exists* is deliberate and safe; its value is
    #: not disclosed.
    masked_fields: list[str] = Field(default_factory=list)


class BulkResult(Schema):
    """Outcome of an operation over many rows.

    Partial success is the normal outcome of a mark upload: 480 rows land and
    six fail because the student numbers do not exist. Reporting that as one
    boolean forces the user to re-upload all 486.
    """

    total: int
    succeeded: int
    failed: int
    errors: list[dict[str, Any]] = Field(default_factory=list)
    correlation_id: uuid.UUID | None = None


class DateRange(Schema):
    start: date
    end: date

    @field_validator("end")
    @classmethod
    def _ordered(cls, v: date, info: Any) -> date:
        start = info.data.get("start")
        if start and v < start:
            raise ValueError("end date is before the start date")
        return v


class Reason(Schema):
    """A required justification.

    Attached to actions whose audit line is meaningless without one. "Fee
    waived" is not an audit record; "fee waived — bereavement, letter on file,
    ref WEL/2026/118" is.
    """

    reason: Annotated[str, Field(min_length=10, max_length=1000)]
    reference: str | None = None
