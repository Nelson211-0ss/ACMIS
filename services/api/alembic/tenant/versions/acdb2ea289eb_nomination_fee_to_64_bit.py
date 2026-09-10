"""Widen the nomination fee to 64-bit.

Written after the sweep in `58be5785ff43` and so missed by it. Caught by
`test_money_is_held_in_64_bit_columns`, which exists for exactly this: a money
column added later is the one that will be 32 bits.

Revision ID: acdb2ea289eb
Revises: c1d2e3f4a5b6
Create Date: 2026-09-09 21:33:37.264137
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "acdb2ea289eb"
down_revision: str | None = "c1d2e3f4a5b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "election_candidate",
        "nomination_fee_minor",
        existing_type=sa.INTEGER(),
        type_=sa.BigInteger(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "election_candidate",
        "nomination_fee_minor",
        existing_type=sa.BigInteger(),
        type_=sa.INTEGER(),
        existing_nullable=True,
    )
