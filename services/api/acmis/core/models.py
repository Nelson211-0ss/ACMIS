"""Declarative bases and the mixins every table in ACMIS shares.

There are two `MetaData` objects, and the split matters: `ControlBase` maps
tables that exist once for the whole platform, `TenantBase` maps tables that
exist once *per university*. Alembic keeps a separate migration tree for each
(`alembic/control/` and `alembic/tenant/`), and a model inheriting the wrong
base is the kind of mistake that shows up as a table appearing in 200
databases that should have appeared in one.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Integer,
    MetaData,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

#: Explicit naming convention so Alembic autogenerate produces stable names.
#: Without it Postgres invents constraint names and a later migration cannot
#: reliably drop them.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_N_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utcnow() -> datetime:
    """Timezone-aware now. Never use `datetime.utcnow()` — it returns naive."""
    return datetime.now(UTC)


class ControlBase(DeclarativeBase):
    """Base for platform-wide tables (one database for the whole fleet)."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION, schema=None)
    type_annotation_map = {dict[str, Any]: JSONB, datetime: DateTime(timezone=True)}


class TenantBase(DeclarativeBase):
    """Base for per-university tables (one database per tenant)."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION, schema=None)
    type_annotation_map = {dict[str, Any]: JSONB, datetime: DateTime(timezone=True)}


class UUIDPrimaryKey:
    """UUIDv4 primary keys, generated in Python.

    Generated application-side rather than by `gen_random_uuid()` so that a
    record's id is known before the INSERT. Half the domain needs this: an
    application's documents are uploaded to object storage under the
    application id while the row is still being built, and a fee invoice's
    payment reference is derived from its id.

    UUIDs, not sequential integers, because ids leave the system — they appear
    in URLs, receipts and API payloads, and a sequential id in a URL tells an
    applicant how many people applied before them.
    """

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class Timestamped:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=utcnow
    )


class Actored:
    """Who created and last changed the row.

    Denormalised onto the row itself even though the audit trail records the
    same fact. The audit trail answers "what happened to this record"; these
    two columns answer "who owns this record right now" without a join, which
    is what every approval queue in the system needs to filter on.
    """

    created_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class SoftDelete:
    """Academic records are never hard-deleted.

    A student who withdrew in 2019 must still be able to request a transcript
    in 2031, and a mark that was entered and then removed is evidence in an
    appeal. `deleted_at` hides the row from normal reads; the row stays.
    """

    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    deleted_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    deletion_reason: Mapped[str | None] = mapped_column(String(500))

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


class Versioned:
    """Optimistic locking.

    Two examiners with the same mark sheet open is the normal case, not the
    edge case. SQLAlchemy raises `StaleDataError` on a version mismatch, which
    the API turns into 409 with the current value, instead of the second save
    silently overwriting the first.
    """

    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    @declared_attr.directive
    def __mapper_args__(cls) -> dict[str, Any]:  # noqa: N805 - SQLAlchemy directive takes `cls`
        return {"version_id_col": cls.__table__.c.version}  # type: ignore[attr-defined]


class TenantRecord(UUIDPrimaryKey, Timestamped, Actored, SoftDelete, TenantBase):
    """What almost every per-university table inherits."""

    __abstract__ = True


class ControlRecord(UUIDPrimaryKey, Timestamped, ControlBase):
    """What almost every platform-wide table inherits."""

    __abstract__ = True


class Effective:
    """Validity window for reference data that changes between intakes.

    A programme's tuition, a grading scale, a fee structure — each is correct
    only for a span of time, and last year's transcript must be recomputed with
    last year's rules. Rows are added, not edited, and reads pick the row whose
    window contains the date in question.
    """

    effective_from: Mapped[date] = mapped_column(nullable=False, index=True)
    effective_to: Mapped[date | None] = mapped_column(index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
