"""Student elections: nominations, ballots, voting and results.

Seven tables, and the split between two of them is the whole design.
`election_voter_roll` knows who may vote and stamps *that* they voted;
`election_ballot` holds the choice and carries no voter column at all. Nothing
joins them — no key, and `cast_at` is truncated to the minute so the two
cannot be lined up by timestamp either.

The next revision makes `election_ballot` append-only in the database, so a
cast ballot cannot be altered even by someone holding the connection.

Revision ID: 7f31dc4e024f
Revises: 58be5785ff43
Create Date: 2026-09-09 21:30:19.272950
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "7f31dc4e024f"
down_revision: str | None = "58be5785ff43"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "election",
        sa.Column("reference", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("academic_year_id", sa.UUID(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("returning_officer_id", sa.UUID(), nullable=True),
        sa.Column("observer_staff_ids", postgresql.ARRAY(sa.UUID()), nullable=False),
        sa.Column("nominations_open_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("nominations_close_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("campaign_starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voting_opens_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voting_closes_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("quorum_percent", sa.Integer(), nullable=True),
        sa.Column("eligible_count", sa.Integer(), nullable=False),
        sa.Column("ballots_cast", sa.Integer(), nullable=False),
        sa.Column("turnout_percent", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opened_by_id", sa.UUID(), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by_id", sa.UUID(), nullable=True),
        sa.Column("declared_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("declared_by_id", sa.UUID(), nullable=True),
        sa.Column("annulled_reason", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.Column("updated_by_id", sa.UUID(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_id", sa.UUID(), nullable=True),
        sa.Column("deletion_reason", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(
            ["academic_year_id"],
            ["academic_year.id"],
            name=op.f("fk_election_academic_year_id_academic_year"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_election")),
        sa.UniqueConstraint("reference", name=op.f("uq_election_reference")),
    )
    op.create_index(
        op.f("ix_election_academic_year_id"), "election", ["academic_year_id"], unique=False
    )
    op.create_index(op.f("ix_election_created_at"), "election", ["created_at"], unique=False)
    op.create_index(op.f("ix_election_created_by_id"), "election", ["created_by_id"], unique=False)
    op.create_index(op.f("ix_election_deleted_at"), "election", ["deleted_at"], unique=False)
    op.create_index(op.f("ix_election_kind"), "election", ["kind"], unique=False)
    op.create_index("ix_election_live", "election", ["status", "voting_closes_at"], unique=False)
    op.create_index(op.f("ix_election_status"), "election", ["status"], unique=False)
    op.create_table(
        "election_position",
        sa.Column("election_id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("seats", sa.Integer(), nullable=False),
        sa.Column("max_choices", sa.Integer(), nullable=False),
        sa.Column("electorate_faculty_ids", postgresql.ARRAY(sa.UUID()), nullable=False),
        sa.Column("electorate_programme_ids", postgresql.ARRAY(sa.UUID()), nullable=False),
        sa.Column("electorate_year_of_study", sa.Integer(), nullable=True),
        sa.Column("reserved_for", sa.String(length=30), nullable=True),
        sa.Column("eligibility_rules", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_referendum", sa.Boolean(), nullable=False),
        sa.Column("question", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.Column("updated_by_id", sa.UUID(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_id", sa.UUID(), nullable=True),
        sa.Column("deletion_reason", sa.String(length=500), nullable=True),
        sa.CheckConstraint(
            "max_choices >= 1", name=op.f("ck_election_position_ck_position_choices")
        ),
        sa.CheckConstraint("seats >= 1", name=op.f("ck_election_position_ck_position_seats")),
        sa.ForeignKeyConstraint(
            ["election_id"],
            ["election.id"],
            name=op.f("fk_election_position_election_id_election"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_election_position")),
        sa.UniqueConstraint("election_id", "code", name="uq_election_position_code"),
    )
    op.create_index(
        op.f("ix_election_position_created_at"), "election_position", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_election_position_created_by_id"),
        "election_position",
        ["created_by_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_election_position_deleted_at"), "election_position", ["deleted_at"], unique=False
    )
    op.create_index(
        op.f("ix_election_position_election_id"), "election_position", ["election_id"], unique=False
    )
    op.create_table(
        "election_voter_roll",
        sa.Column("election_id", sa.UUID(), nullable=False),
        sa.Column("student_id", sa.UUID(), nullable=False),
        sa.Column("position_ids", postgresql.ARRAY(sa.UUID()), nullable=False),
        sa.Column("faculty_ids", postgresql.ARRAY(sa.UUID()), nullable=False),
        sa.Column("programme_ids", postgresql.ARRAY(sa.UUID()), nullable=False),
        sa.Column("year_of_study", sa.Integer(), nullable=True),
        sa.Column("is_eligible", sa.Boolean(), nullable=False),
        sa.Column("ineligible_reason", sa.String(length=300), nullable=True),
        sa.Column("voted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voted_via", sa.String(length=20), nullable=True),
        sa.Column("voted_ip_hash", sa.String(length=64), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.Column("updated_by_id", sa.UUID(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_id", sa.UUID(), nullable=True),
        sa.Column("deletion_reason", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(
            ["election_id"],
            ["election.id"],
            name=op.f("fk_election_voter_roll_election_id_election"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["student.id"],
            name=op.f("fk_election_voter_roll_student_id_student"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_election_voter_roll")),
        sa.UniqueConstraint("election_id", "student_id", name="uq_voter_roll_once"),
    )
    op.create_index(
        op.f("ix_election_voter_roll_created_at"),
        "election_voter_roll",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_election_voter_roll_created_by_id"),
        "election_voter_roll",
        ["created_by_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_election_voter_roll_deleted_at"),
        "election_voter_roll",
        ["deleted_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_election_voter_roll_election_id"),
        "election_voter_roll",
        ["election_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_election_voter_roll_is_eligible"),
        "election_voter_roll",
        ["is_eligible"],
        unique=False,
    )
    op.create_index(
        op.f("ix_election_voter_roll_student_id"),
        "election_voter_roll",
        ["student_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_election_voter_roll_voted_at"), "election_voter_roll", ["voted_at"], unique=False
    )
    op.create_table(
        "election_ballot",
        sa.Column("election_id", sa.UUID(), nullable=False),
        sa.Column("position_id", sa.UUID(), nullable=False),
        sa.Column("candidate_ids", postgresql.ARRAY(sa.UUID()), nullable=False),
        sa.Column("is_abstention", sa.Boolean(), nullable=False),
        sa.Column("is_spoilt", sa.Boolean(), nullable=False),
        sa.Column("cast_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("receipt_token", sa.String(length=40), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.Column("updated_by_id", sa.UUID(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_id", sa.UUID(), nullable=True),
        sa.Column("deletion_reason", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(
            ["election_id"],
            ["election.id"],
            name=op.f("fk_election_ballot_election_id_election"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["position_id"],
            ["election_position.id"],
            name=op.f("fk_election_ballot_position_id_election_position"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_election_ballot")),
    )
    op.create_index(
        "ix_ballot_count", "election_ballot", ["election_id", "position_id"], unique=False
    )
    op.create_index(
        op.f("ix_election_ballot_created_at"), "election_ballot", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_election_ballot_created_by_id"), "election_ballot", ["created_by_id"], unique=False
    )
    op.create_index(
        op.f("ix_election_ballot_deleted_at"), "election_ballot", ["deleted_at"], unique=False
    )
    op.create_index(
        op.f("ix_election_ballot_election_id"), "election_ballot", ["election_id"], unique=False
    )
    op.create_index(
        op.f("ix_election_ballot_position_id"), "election_ballot", ["position_id"], unique=False
    )
    op.create_index(
        op.f("ix_election_ballot_receipt_token"), "election_ballot", ["receipt_token"], unique=True
    )
    op.create_table(
        "election_candidate",
        sa.Column("position_id", sa.UUID(), nullable=False),
        sa.Column("student_id", sa.UUID(), nullable=True),
        sa.Column("option_label", sa.String(length=60), nullable=True),
        sa.Column("ballot_name", sa.String(length=200), nullable=False),
        sa.Column("ballot_order", sa.Integer(), nullable=False),
        sa.Column("slogan", sa.String(length=200), nullable=True),
        sa.Column("manifesto", sa.Text(), nullable=True),
        sa.Column("photo_attachment_id", sa.UUID(), nullable=True),
        sa.Column("nominator_student_ids", postgresql.ARRAY(sa.UUID()), nullable=False),
        sa.Column("nomination_fee_minor", sa.Integer(), nullable=True),
        sa.Column("nomination_fee_invoice_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("nominated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("vetted_by_id", sa.UUID(), nullable=True),
        sa.Column("vetted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("eligibility_checks", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("disqualification_reason", sa.Text(), nullable=True),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("votes", sa.Integer(), nullable=False),
        sa.Column("is_elected", sa.Boolean(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.Column("updated_by_id", sa.UUID(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_id", sa.UUID(), nullable=True),
        sa.Column("deletion_reason", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(
            ["position_id"],
            ["election_position.id"],
            name=op.f("fk_election_candidate_position_id_election_position"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["student.id"],
            name=op.f("fk_election_candidate_student_id_student"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_election_candidate")),
        sa.UniqueConstraint("position_id", "student_id", name="uq_candidate_once"),
    )
    op.create_index(
        "ix_candidate_ballot", "election_candidate", ["position_id", "ballot_order"], unique=False
    )
    op.create_index(
        op.f("ix_election_candidate_created_at"), "election_candidate", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_election_candidate_created_by_id"),
        "election_candidate",
        ["created_by_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_election_candidate_deleted_at"), "election_candidate", ["deleted_at"], unique=False
    )
    op.create_index(
        op.f("ix_election_candidate_position_id"),
        "election_candidate",
        ["position_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_election_candidate_status"), "election_candidate", ["status"], unique=False
    )
    op.create_index(
        op.f("ix_election_candidate_student_id"), "election_candidate", ["student_id"], unique=False
    )
    op.create_table(
        "election_petition",
        sa.Column("reference", sa.String(length=40), nullable=False),
        sa.Column("election_id", sa.UUID(), nullable=False),
        sa.Column("position_id", sa.UUID(), nullable=True),
        sa.Column("petitioner_student_id", sa.UUID(), nullable=True),
        sa.Column("ground", sa.String(length=30), nullable=False),
        sa.Column("submission", sa.Text(), nullable=False),
        sa.Column("evidence_attachment_ids", postgresql.ARRAY(sa.UUID()), nullable=False),
        sa.Column("filed_on", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("heard_on", sa.Date(), nullable=True),
        sa.Column("panel_staff_ids", postgresql.ARRAY(sa.UUID()), nullable=False),
        sa.Column("determination", sa.Text(), nullable=True),
        sa.Column("remedy", sa.String(length=30), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.Column("updated_by_id", sa.UUID(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_id", sa.UUID(), nullable=True),
        sa.Column("deletion_reason", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(
            ["election_id"],
            ["election.id"],
            name=op.f("fk_election_petition_election_id_election"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["petitioner_student_id"],
            ["student.id"],
            name=op.f("fk_election_petition_petitioner_student_id_student"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["position_id"],
            ["election_position.id"],
            name=op.f("fk_election_petition_position_id_election_position"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_election_petition")),
        sa.UniqueConstraint("reference", name=op.f("uq_election_petition_reference")),
    )
    op.create_index(
        op.f("ix_election_petition_created_at"), "election_petition", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_election_petition_created_by_id"),
        "election_petition",
        ["created_by_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_election_petition_deleted_at"), "election_petition", ["deleted_at"], unique=False
    )
    op.create_index(
        op.f("ix_election_petition_election_id"), "election_petition", ["election_id"], unique=False
    )
    op.create_index(
        op.f("ix_election_petition_petitioner_student_id"),
        "election_petition",
        ["petitioner_student_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_election_petition_status"), "election_petition", ["status"], unique=False
    )
    op.create_table(
        "election_result",
        sa.Column("election_id", sa.UUID(), nullable=False),
        sa.Column("position_id", sa.UUID(), nullable=False),
        sa.Column("eligible_count", sa.Integer(), nullable=False),
        sa.Column("ballots_cast", sa.Integer(), nullable=False),
        sa.Column("abstentions", sa.Integer(), nullable=False),
        sa.Column("spoilt", sa.Integer(), nullable=False),
        sa.Column("turnout_percent", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("tally", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("quorum_met", sa.Boolean(), nullable=True),
        sa.Column("declared_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("declared_by_id", sa.UUID(), nullable=True),
        sa.Column("tie_break_note", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.Column("updated_by_id", sa.UUID(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_id", sa.UUID(), nullable=True),
        sa.Column("deletion_reason", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(
            ["election_id"],
            ["election.id"],
            name=op.f("fk_election_result_election_id_election"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["position_id"],
            ["election_position.id"],
            name=op.f("fk_election_result_position_id_election_position"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_election_result")),
        sa.UniqueConstraint("election_id", "position_id", name="uq_result_position"),
    )
    op.create_index(
        op.f("ix_election_result_created_at"), "election_result", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_election_result_created_by_id"), "election_result", ["created_by_id"], unique=False
    )
    op.create_index(
        op.f("ix_election_result_deleted_at"), "election_result", ["deleted_at"], unique=False
    )
    op.create_index(
        op.f("ix_election_result_election_id"), "election_result", ["election_id"], unique=False
    )
    op.create_index(
        op.f("ix_election_result_position_id"), "election_result", ["position_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_election_result_position_id"), table_name="election_result")
    op.drop_index(op.f("ix_election_result_election_id"), table_name="election_result")
    op.drop_index(op.f("ix_election_result_deleted_at"), table_name="election_result")
    op.drop_index(op.f("ix_election_result_created_by_id"), table_name="election_result")
    op.drop_index(op.f("ix_election_result_created_at"), table_name="election_result")
    op.drop_table("election_result")
    op.drop_index(op.f("ix_election_petition_status"), table_name="election_petition")
    op.drop_index(
        op.f("ix_election_petition_petitioner_student_id"), table_name="election_petition"
    )
    op.drop_index(op.f("ix_election_petition_election_id"), table_name="election_petition")
    op.drop_index(op.f("ix_election_petition_deleted_at"), table_name="election_petition")
    op.drop_index(op.f("ix_election_petition_created_by_id"), table_name="election_petition")
    op.drop_index(op.f("ix_election_petition_created_at"), table_name="election_petition")
    op.drop_table("election_petition")
    op.drop_index(op.f("ix_election_candidate_student_id"), table_name="election_candidate")
    op.drop_index(op.f("ix_election_candidate_status"), table_name="election_candidate")
    op.drop_index(op.f("ix_election_candidate_position_id"), table_name="election_candidate")
    op.drop_index(op.f("ix_election_candidate_deleted_at"), table_name="election_candidate")
    op.drop_index(op.f("ix_election_candidate_created_by_id"), table_name="election_candidate")
    op.drop_index(op.f("ix_election_candidate_created_at"), table_name="election_candidate")
    op.drop_index("ix_candidate_ballot", table_name="election_candidate")
    op.drop_table("election_candidate")
    op.drop_index(op.f("ix_election_ballot_receipt_token"), table_name="election_ballot")
    op.drop_index(op.f("ix_election_ballot_position_id"), table_name="election_ballot")
    op.drop_index(op.f("ix_election_ballot_election_id"), table_name="election_ballot")
    op.drop_index(op.f("ix_election_ballot_deleted_at"), table_name="election_ballot")
    op.drop_index(op.f("ix_election_ballot_created_by_id"), table_name="election_ballot")
    op.drop_index(op.f("ix_election_ballot_created_at"), table_name="election_ballot")
    op.drop_index("ix_ballot_count", table_name="election_ballot")
    op.drop_table("election_ballot")
    op.drop_index(op.f("ix_election_voter_roll_voted_at"), table_name="election_voter_roll")
    op.drop_index(op.f("ix_election_voter_roll_student_id"), table_name="election_voter_roll")
    op.drop_index(op.f("ix_election_voter_roll_is_eligible"), table_name="election_voter_roll")
    op.drop_index(op.f("ix_election_voter_roll_election_id"), table_name="election_voter_roll")
    op.drop_index(op.f("ix_election_voter_roll_deleted_at"), table_name="election_voter_roll")
    op.drop_index(op.f("ix_election_voter_roll_created_by_id"), table_name="election_voter_roll")
    op.drop_index(op.f("ix_election_voter_roll_created_at"), table_name="election_voter_roll")
    op.drop_table("election_voter_roll")
    op.drop_index(op.f("ix_election_position_election_id"), table_name="election_position")
    op.drop_index(op.f("ix_election_position_deleted_at"), table_name="election_position")
    op.drop_index(op.f("ix_election_position_created_by_id"), table_name="election_position")
    op.drop_index(op.f("ix_election_position_created_at"), table_name="election_position")
    op.drop_table("election_position")
    op.drop_index(op.f("ix_election_status"), table_name="election")
    op.drop_index("ix_election_live", table_name="election")
    op.drop_index(op.f("ix_election_kind"), table_name="election")
    op.drop_index(op.f("ix_election_deleted_at"), table_name="election")
    op.drop_index(op.f("ix_election_created_by_id"), table_name="election")
    op.drop_index(op.f("ix_election_created_at"), table_name="election")
    op.drop_index(op.f("ix_election_academic_year_id"), table_name="election")
    op.drop_table("election")
