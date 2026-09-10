"""Split the composite GIN index on `course_offering`.

The original declared `USING gin (semester_id, department_ids)` — a scalar
`uuid` alongside a `uuid[]`. Postgres has no default GIN operator class for a
scalar uuid, so the index would not build at all without `btree_gin`, and the
first tenant provisioned from `template0` (which is what provisioning uses, so
a tenant never inherits whatever is in `template1`) failed its migration on
exactly this.

The fix is not to add the extension dependency but to drop the composite: the
planner combines a GIN on the array with the existing btree on `semester_id`
through a bitmap scan, which is what it would have done anyway. `btree_gin` is
still installed per tenant — several other indexes want it — but this one no
longer needs it.

A new migration rather than an edit to the initial one, for the same reason as
always: an applied migration is a fact about the databases that ran it, and
editing it makes two populations of tenant silently diverge.

Revision ID: a7b8c9d0e1f2
Revises: f1a2b3c4d5e6
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "a7b8c9d0e1f2"
down_revision: str | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_offering_semester_dept")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_offering_departments "
        "ON course_offering USING gin (department_ids)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_offering_departments")
    # The composite form needs `btree_gin` for its scalar half.
    op.execute('CREATE EXTENSION IF NOT EXISTS "btree_gin"')
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_offering_semester_dept "
        "ON course_offering USING gin (semester_id, department_ids)"
    )
