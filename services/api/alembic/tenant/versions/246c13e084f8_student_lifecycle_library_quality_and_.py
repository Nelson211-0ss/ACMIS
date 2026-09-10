"""Student lifecycle, library, quality assurance and late payments.

Thirty-one tables across four areas, in one revision because they arrived as
one body of work and splitting them would give a half-migrated tenant no
useful intermediate state:

* **Student life-cycle** — special and supplementary examination requests,
  campus identity cards, examination cards, and transfers between
  institutions. Dead semesters and course changes needed no new table: they
  are `student_status_change` and `programme_transfer` rows, which already
  carry the approval chain and the evidence.
* **The library** — catalogue records and their copies, members, loans,
  reservations, fines, acquisitions, e-resource subscriptions and stock-takes.
* **Quality assurance** — class sessions and per-session attendance for
  students and staff, evaluation instruments and their anonymous responses,
  teaching observations, audits and indicators.
* **Late payment** — the rules, the surcharges actually applied, instalment
  plans and the reminders sent.

Revision ID: 246c13e084f8
Revises: a7b8c9d0e1f2
Create Date: 2026-09-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "246c13e084f8"
down_revision: str | None = "a7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "e_resource_subscription",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("provider", sa.String(length=200), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("access_url", sa.String(length=600), nullable=True),
        sa.Column("authentication_method", sa.String(length=30), nullable=True),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("expires_on", sa.Date(), nullable=False),
        sa.Column("concurrent_users", sa.Integer(), nullable=True),
        sa.Column("annual_cost_minor", sa.Integer(), nullable=True),
        sa.Column("unit_ids", postgresql.ARRAY(sa.UUID()), nullable=False),
        sa.Column("usage_statistics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("renewal_decision_due_on", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_e_resource_subscription")),
    )
    op.create_index(
        op.f("ix_e_resource_subscription_created_at"),
        "e_resource_subscription",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_e_resource_subscription_created_by_id"),
        "e_resource_subscription",
        ["created_by_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_e_resource_subscription_deleted_at"),
        "e_resource_subscription",
        ["deleted_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_e_resource_subscription_expires_on"),
        "e_resource_subscription",
        ["expires_on"],
        unique=False,
    )
    op.create_index(
        op.f("ix_e_resource_subscription_is_active"),
        "e_resource_subscription",
        ["is_active"],
        unique=False,
    )
    op.create_table(
        "evaluation_instrument",
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("introduction", sa.Text(), nullable=True),
        sa.Column("questions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("dimensions", postgresql.ARRAY(sa.String(length=60)), nullable=False),
        sa.Column("is_published", sa.Boolean(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evaluation_instrument")),
        sa.UniqueConstraint("code", "version", name="uq_instrument_version"),
    )
    op.create_index(
        op.f("ix_evaluation_instrument_created_at"),
        "evaluation_instrument",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_evaluation_instrument_created_by_id"),
        "evaluation_instrument",
        ["created_by_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_evaluation_instrument_deleted_at"),
        "evaluation_instrument",
        ["deleted_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_evaluation_instrument_is_published"),
        "evaluation_instrument",
        ["is_published"],
        unique=False,
    )
    op.create_table(
        "catalogue_record",
        sa.Column("material_kind", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=400), nullable=False),
        sa.Column("subtitle", sa.String(length=400), nullable=True),
        sa.Column("statement_of_responsibility", sa.String(length=400), nullable=True),
        sa.Column("authors", postgresql.ARRAY(sa.String(length=200)), nullable=False),
        sa.Column("edition", sa.String(length=60), nullable=True),
        sa.Column("publisher", sa.String(length=200), nullable=True),
        sa.Column("place_of_publication", sa.String(length=120), nullable=True),
        sa.Column("published_year", sa.Integer(), nullable=True),
        sa.Column("isbn", sa.String(length=20), nullable=True),
        sa.Column("issn", sa.String(length=12), nullable=True),
        sa.Column("doi", sa.String(length=120), nullable=True),
        sa.Column("language", sa.String(length=3), nullable=False),
        sa.Column("classification", sa.String(length=40), nullable=True),
        sa.Column("author_mark", sa.String(length=20), nullable=True),
        sa.Column("subjects", postgresql.ARRAY(sa.String(length=120)), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("course_ids", postgresql.ARRAY(sa.UUID()), nullable=False),
        sa.Column("online_url", sa.String(length=600), nullable=True),
        sa.Column("attachment_id", sa.UUID(), nullable=True),
        sa.Column("cover_attachment_id", sa.UUID(), nullable=True),
        sa.Column("marc_fields", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("student_id", sa.UUID(), nullable=True),
        sa.Column("is_searchable", sa.Boolean(), nullable=False),
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
            ["student_id"],
            ["student.id"],
            name=op.f("fk_catalogue_record_student_id_student"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_catalogue_record")),
    )
    op.create_index(
        op.f("ix_catalogue_record_classification"),
        "catalogue_record",
        ["classification"],
        unique=False,
    )
    op.create_index(
        op.f("ix_catalogue_record_created_at"), "catalogue_record", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_catalogue_record_created_by_id"),
        "catalogue_record",
        ["created_by_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_catalogue_record_deleted_at"), "catalogue_record", ["deleted_at"], unique=False
    )
    op.create_index(
        op.f("ix_catalogue_record_is_searchable"),
        "catalogue_record",
        ["is_searchable"],
        unique=False,
    )
    op.create_index(op.f("ix_catalogue_record_isbn"), "catalogue_record", ["isbn"], unique=False)
    op.create_index(op.f("ix_catalogue_record_issn"), "catalogue_record", ["issn"], unique=False)
    op.create_index(
        op.f("ix_catalogue_record_material_kind"),
        "catalogue_record",
        ["material_kind"],
        unique=False,
    )
    op.create_index(
        op.f("ix_catalogue_record_published_year"),
        "catalogue_record",
        ["published_year"],
        unique=False,
    )
    op.create_index(
        op.f("ix_catalogue_record_student_id"), "catalogue_record", ["student_id"], unique=False
    )
    op.create_index("ix_catalogue_title", "catalogue_record", ["title"], unique=False)
    op.create_table(
        "library",
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("campus_id", sa.UUID(), nullable=True),
        sa.Column("location_note", sa.String(length=300), nullable=True),
        sa.Column("email", sa.String(length=200), nullable=True),
        sa.Column("phone", sa.String(length=40), nullable=True),
        sa.Column("opening_hours", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
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
            ["campus_id"],
            ["campus.id"],
            name=op.f("fk_library_campus_id_campus"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_library")),
        sa.UniqueConstraint("code", name=op.f("uq_library_code")),
    )
    op.create_index(op.f("ix_library_campus_id"), "library", ["campus_id"], unique=False)
    op.create_index(op.f("ix_library_created_at"), "library", ["created_at"], unique=False)
    op.create_index(op.f("ix_library_created_by_id"), "library", ["created_by_id"], unique=False)
    op.create_index(op.f("ix_library_deleted_at"), "library", ["deleted_at"], unique=False)
    op.create_table(
        "student_id_card",
        sa.Column("student_id", sa.UUID(), nullable=False),
        sa.Column("serial", sa.String(length=40), nullable=False),
        sa.Column("barcode", sa.String(length=60), nullable=True),
        sa.Column("rfid_uid", sa.String(length=60), nullable=True),
        sa.Column("photo_attachment_id", sa.UUID(), nullable=True),
        sa.Column("campus_id", sa.UUID(), nullable=True),
        sa.Column("issued_on", sa.Date(), nullable=False),
        sa.Column("expires_on", sa.Date(), nullable=True),
        sa.Column("reason", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("reported_lost_on", sa.Date(), nullable=True),
        sa.Column("replacement_fee_minor", sa.Integer(), nullable=True),
        sa.Column("fee_invoice_id", sa.UUID(), nullable=True),
        sa.Column("supersedes_card_id", sa.UUID(), nullable=True),
        sa.Column("issued_by_id", sa.UUID(), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=True),
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
            ["campus_id"],
            ["campus.id"],
            name=op.f("fk_student_id_card_campus_id_campus"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["student.id"],
            name=op.f("fk_student_id_card_student_id_student"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_student_id_card")),
        sa.UniqueConstraint("rfid_uid", name=op.f("uq_student_id_card_rfid_uid")),
    )
    op.create_index("ix_id_card_live", "student_id_card", ["student_id", "status"], unique=False)
    op.create_index(op.f("ix_student_id_card_barcode"), "student_id_card", ["barcode"], unique=True)
    op.create_index(
        op.f("ix_student_id_card_created_at"), "student_id_card", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_student_id_card_created_by_id"), "student_id_card", ["created_by_id"], unique=False
    )
    op.create_index(
        op.f("ix_student_id_card_deleted_at"), "student_id_card", ["deleted_at"], unique=False
    )
    op.create_index(
        op.f("ix_student_id_card_expires_on"), "student_id_card", ["expires_on"], unique=False
    )
    op.create_index(
        op.f("ix_student_id_card_issued_on"), "student_id_card", ["issued_on"], unique=False
    )
    op.create_index(op.f("ix_student_id_card_serial"), "student_id_card", ["serial"], unique=True)
    op.create_index(op.f("ix_student_id_card_status"), "student_id_card", ["status"], unique=False)
    op.create_index(
        op.f("ix_student_id_card_student_id"), "student_id_card", ["student_id"], unique=False
    )
    op.create_table(
        "calendar_event",
        sa.Column("academic_year_id", sa.UUID(), nullable=False),
        sa.Column("semester_id", sa.UUID(), nullable=True),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=False),
        sa.Column("starts_at", sa.String(length=5), nullable=True),
        sa.Column("ends_at", sa.String(length=5), nullable=True),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("unit_ids", postgresql.ARRAY(sa.UUID()), nullable=False),
        sa.Column("campus_ids", postgresql.ARRAY(sa.UUID()), nullable=False),
        sa.Column("audience", sa.String(length=20), nullable=False),
        sa.Column("suspends_teaching", sa.Boolean(), nullable=False),
        sa.Column("is_published", sa.Boolean(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("minute_reference", sa.String(length=80), nullable=True),
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
            "ends_on >= starts_on", name=op.f("ck_calendar_event_ck_calendar_event_range")
        ),
        sa.ForeignKeyConstraint(
            ["academic_year_id"],
            ["academic_year.id"],
            name=op.f("fk_calendar_event_academic_year_id_academic_year"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["semester_id"],
            ["semester.id"],
            name=op.f("fk_calendar_event_semester_id_semester"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_calendar_event")),
    )
    op.create_index(
        op.f("ix_calendar_event_academic_year_id"),
        "calendar_event",
        ["academic_year_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_calendar_event_audience"), "calendar_event", ["audience"], unique=False
    )
    op.create_index(
        op.f("ix_calendar_event_created_at"), "calendar_event", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_calendar_event_created_by_id"), "calendar_event", ["created_by_id"], unique=False
    )
    op.create_index(
        op.f("ix_calendar_event_deleted_at"), "calendar_event", ["deleted_at"], unique=False
    )
    op.create_index(
        op.f("ix_calendar_event_is_published"), "calendar_event", ["is_published"], unique=False
    )
    op.create_index(op.f("ix_calendar_event_kind"), "calendar_event", ["kind"], unique=False)
    op.create_index(
        op.f("ix_calendar_event_semester_id"), "calendar_event", ["semester_id"], unique=False
    )
    op.create_index(
        op.f("ix_calendar_event_starts_on"), "calendar_event", ["starts_on"], unique=False
    )
    op.create_index(
        "ix_calendar_event_window",
        "calendar_event",
        ["academic_year_id", "starts_on", "ends_on"],
        unique=False,
    )
    op.create_table(
        "catalogue_copy",
        sa.Column("record_id", sa.UUID(), nullable=False),
        sa.Column("library_id", sa.UUID(), nullable=False),
        sa.Column("accession_number", sa.String(length=40), nullable=False),
        sa.Column("barcode", sa.String(length=60), nullable=False),
        sa.Column("call_number", sa.String(length=80), nullable=True),
        sa.Column("shelf_location", sa.String(length=80), nullable=True),
        sa.Column("loan_class", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("condition", sa.String(length=20), nullable=False),
        sa.Column("acquired_on", sa.Date(), nullable=True),
        sa.Column("price_minor", sa.Integer(), nullable=True),
        sa.Column("supplier", sa.String(length=200), nullable=True),
        sa.Column("last_seen_on", sa.Date(), nullable=True),
        sa.Column("withdrawn_on", sa.Date(), nullable=True),
        sa.Column("withdrawal_reason", sa.String(length=300), nullable=True),
        sa.Column("times_issued", sa.Integer(), nullable=False),
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
            ["library_id"],
            ["library.id"],
            name=op.f("fk_catalogue_copy_library_id_library"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["record_id"],
            ["catalogue_record.id"],
            name=op.f("fk_catalogue_copy_record_id_catalogue_record"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_catalogue_copy")),
        sa.UniqueConstraint("accession_number", name=op.f("uq_catalogue_copy_accession_number")),
    )
    op.create_index(op.f("ix_catalogue_copy_barcode"), "catalogue_copy", ["barcode"], unique=True)
    op.create_index(
        op.f("ix_catalogue_copy_call_number"), "catalogue_copy", ["call_number"], unique=False
    )
    op.create_index(
        op.f("ix_catalogue_copy_created_at"), "catalogue_copy", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_catalogue_copy_created_by_id"), "catalogue_copy", ["created_by_id"], unique=False
    )
    op.create_index(
        op.f("ix_catalogue_copy_deleted_at"), "catalogue_copy", ["deleted_at"], unique=False
    )
    op.create_index(
        op.f("ix_catalogue_copy_library_id"), "catalogue_copy", ["library_id"], unique=False
    )
    op.create_index(
        op.f("ix_catalogue_copy_record_id"), "catalogue_copy", ["record_id"], unique=False
    )
    op.create_index(op.f("ix_catalogue_copy_status"), "catalogue_copy", ["status"], unique=False)
    op.create_index(
        "ix_copy_shelf", "catalogue_copy", ["library_id", "status", "call_number"], unique=False
    )
    op.create_table(
        "library_stock_take",
        sa.Column("reference", sa.String(length=40), nullable=False),
        sa.Column("library_id", sa.UUID(), nullable=False),
        sa.Column("classification_from", sa.String(length=40), nullable=True),
        sa.Column("classification_to", sa.String(length=40), nullable=True),
        sa.Column("started_on", sa.Date(), nullable=False),
        sa.Column("completed_on", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("expected_count", sa.Integer(), nullable=False),
        sa.Column("seen_count", sa.Integer(), nullable=False),
        sa.Column("missing_copy_ids", postgresql.ARRAY(sa.UUID()), nullable=False),
        sa.Column("misplaced_copy_ids", postgresql.ARRAY(sa.UUID()), nullable=False),
        sa.Column("conducted_by_id", sa.UUID(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
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
            ["library_id"],
            ["library.id"],
            name=op.f("fk_library_stock_take_library_id_library"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_library_stock_take")),
        sa.UniqueConstraint("reference", name=op.f("uq_library_stock_take_reference")),
    )
    op.create_index(
        op.f("ix_library_stock_take_created_at"), "library_stock_take", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_library_stock_take_created_by_id"),
        "library_stock_take",
        ["created_by_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_library_stock_take_deleted_at"), "library_stock_take", ["deleted_at"], unique=False
    )
    op.create_index(
        op.f("ix_library_stock_take_library_id"), "library_stock_take", ["library_id"], unique=False
    )
    op.create_index(
        op.f("ix_library_stock_take_status"), "library_stock_take", ["status"], unique=False
    )
    op.create_table(
        "loan_policy",
        sa.Column("library_id", sa.UUID(), nullable=True),
        sa.Column("borrower_category", sa.String(length=30), nullable=False),
        sa.Column("loan_class", sa.String(length=30), nullable=False),
        sa.Column("loan_days", sa.Integer(), nullable=False),
        sa.Column("max_copies", sa.Integer(), nullable=False),
        sa.Column("max_renewals", sa.Integer(), nullable=False),
        sa.Column("fine_per_day_minor", sa.Integer(), nullable=False),
        sa.Column("fine_cap_minor", sa.Integer(), nullable=True),
        sa.Column("borrowing_block_debt_minor", sa.Integer(), nullable=True),
        sa.Column("grace_days", sa.Integer(), nullable=False),
        sa.Column("reservations_allowed", sa.Boolean(), nullable=False),
        sa.Column("recallable", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
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
        sa.CheckConstraint("loan_days > 0", name=op.f("ck_loan_policy_ck_loan_days_positive")),
        sa.ForeignKeyConstraint(
            ["library_id"],
            ["library.id"],
            name=op.f("fk_loan_policy_library_id_library"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_loan_policy")),
        sa.UniqueConstraint("library_id", "borrower_category", "loan_class", name="uq_loan_policy"),
    )
    op.create_index(
        op.f("ix_loan_policy_borrower_category"), "loan_policy", ["borrower_category"], unique=False
    )
    op.create_index(op.f("ix_loan_policy_created_at"), "loan_policy", ["created_at"], unique=False)
    op.create_index(
        op.f("ix_loan_policy_created_by_id"), "loan_policy", ["created_by_id"], unique=False
    )
    op.create_index(op.f("ix_loan_policy_deleted_at"), "loan_policy", ["deleted_at"], unique=False)
    op.create_index(op.f("ix_loan_policy_library_id"), "loan_policy", ["library_id"], unique=False)
    op.create_table(
        "acquisition_request",
        sa.Column("reference", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=400), nullable=False),
        sa.Column("authors", sa.String(length=400), nullable=True),
        sa.Column("isbn", sa.String(length=20), nullable=True),
        sa.Column("publisher", sa.String(length=200), nullable=True),
        sa.Column("edition", sa.String(length=60), nullable=True),
        sa.Column("copies_requested", sa.Integer(), nullable=False),
        sa.Column("requested_by_id", sa.UUID(), nullable=True),
        sa.Column("requesting_unit_id", sa.UUID(), nullable=True),
        sa.Column("course_id", sa.UUID(), nullable=True),
        sa.Column("expected_cohort", sa.Integer(), nullable=True),
        sa.Column("justification", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("requested_on", sa.Date(), nullable=False),
        sa.Column("estimated_unit_price_minor", sa.Integer(), nullable=True),
        sa.Column("approved_budget_minor", sa.Integer(), nullable=True),
        sa.Column("approved_by_id", sa.UUID(), nullable=True),
        sa.Column("approved_on", sa.Date(), nullable=True),
        sa.Column("decline_reason", sa.Text(), nullable=True),
        sa.Column("supplier", sa.String(length=200), nullable=True),
        sa.Column("order_reference", sa.String(length=60), nullable=True),
        sa.Column("ordered_on", sa.Date(), nullable=True),
        sa.Column("received_on", sa.Date(), nullable=True),
        sa.Column("copies_received", sa.Integer(), nullable=False),
        sa.Column("record_id", sa.UUID(), nullable=True),
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
            ["course_id"],
            ["course.id"],
            name=op.f("fk_acquisition_request_course_id_course"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["record_id"],
            ["catalogue_record.id"],
            name=op.f("fk_acquisition_request_record_id_catalogue_record"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["requesting_unit_id"],
            ["academic_unit.id"],
            name=op.f("fk_acquisition_request_requesting_unit_id_academic_unit"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_acquisition_request")),
        sa.UniqueConstraint("reference", name=op.f("uq_acquisition_request_reference")),
    )
    op.create_index(
        op.f("ix_acquisition_request_course_id"), "acquisition_request", ["course_id"], unique=False
    )
    op.create_index(
        op.f("ix_acquisition_request_created_at"),
        "acquisition_request",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_acquisition_request_created_by_id"),
        "acquisition_request",
        ["created_by_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_acquisition_request_deleted_at"),
        "acquisition_request",
        ["deleted_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_acquisition_request_status"), "acquisition_request", ["status"], unique=False
    )
    op.create_table(
        "late_payment_rule",
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("academic_year_id", sa.UUID(), nullable=False),
        sa.Column("programme_id", sa.UUID(), nullable=True),
        sa.Column("sponsorship", sa.String(length=30), nullable=True),
        sa.Column("applies_to_invoice_kind", sa.String(length=30), nullable=False),
        sa.Column("grace_days", sa.Integer(), nullable=False),
        sa.Column("charge_basis", sa.String(length=20), nullable=False),
        sa.Column("charge_percent", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("charge_flat_minor", sa.Integer(), nullable=True),
        sa.Column("recurrence", sa.String(length=20), nullable=False),
        sa.Column("max_charges", sa.Integer(), nullable=True),
        sa.Column("charge_cap_minor", sa.Integer(), nullable=True),
        sa.Column("blocks_registration_after_days", sa.Integer(), nullable=True),
        sa.Column("blocks_exam_card_after_days", sa.Integer(), nullable=True),
        sa.Column("blocks_results_after_days", sa.Integer(), nullable=True),
        sa.Column("is_waivable", sa.Boolean(), nullable=False),
        sa.Column("charge_fee_item_code", sa.String(length=40), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("approved_by_id", sa.UUID(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
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
            "charge_basis IN ('percentage', 'flat')",
            name=op.f("ck_late_payment_rule_ck_late_charge_basis"),
        ),
        sa.ForeignKeyConstraint(
            ["academic_year_id"],
            ["academic_year.id"],
            name=op.f("fk_late_payment_rule_academic_year_id_academic_year"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["programme_id"],
            ["programme.id"],
            name=op.f("fk_late_payment_rule_programme_id_programme"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_late_payment_rule")),
        sa.UniqueConstraint("academic_year_id", "code", name="uq_late_payment_rule_code"),
    )
    op.create_index(
        op.f("ix_late_payment_rule_academic_year_id"),
        "late_payment_rule",
        ["academic_year_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_late_payment_rule_created_at"), "late_payment_rule", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_late_payment_rule_created_by_id"),
        "late_payment_rule",
        ["created_by_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_late_payment_rule_deleted_at"), "late_payment_rule", ["deleted_at"], unique=False
    )
    op.create_index(
        op.f("ix_late_payment_rule_programme_id"),
        "late_payment_rule",
        ["programme_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_late_payment_rule_sponsorship"), "late_payment_rule", ["sponsorship"], unique=False
    )
    op.create_index(
        op.f("ix_late_payment_rule_status"), "late_payment_rule", ["status"], unique=False
    )
    op.create_table(
        "quality_audit",
        sa.Column("reference", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("unit_id", sa.UUID(), nullable=True),
        sa.Column("programme_id", sa.UUID(), nullable=True),
        sa.Column("standard", sa.String(length=200), nullable=True),
        sa.Column("period_from", sa.Date(), nullable=True),
        sa.Column("period_to", sa.Date(), nullable=True),
        sa.Column("conducted_on", sa.Date(), nullable=True),
        sa.Column("lead_auditor_id", sa.UUID(), nullable=True),
        sa.Column("panel_staff_ids", postgresql.ARRAY(sa.UUID()), nullable=False),
        sa.Column("external_panel", postgresql.ARRAY(sa.String(length=200)), nullable=False),
        sa.Column("findings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("major_findings", sa.Integer(), nullable=False),
        sa.Column("minor_findings", sa.Integer(), nullable=False),
        sa.Column("open_findings", sa.Integer(), nullable=False),
        sa.Column("overall_outcome", sa.String(length=60), nullable=True),
        sa.Column("report_attachment_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_review_due_on", sa.Date(), nullable=True),
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
            ["programme_id"],
            ["programme.id"],
            name=op.f("fk_quality_audit_programme_id_programme"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["unit_id"],
            ["academic_unit.id"],
            name=op.f("fk_quality_audit_unit_id_academic_unit"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quality_audit")),
        sa.UniqueConstraint("reference", name=op.f("uq_quality_audit_reference")),
    )
    op.create_index(
        op.f("ix_quality_audit_conducted_on"), "quality_audit", ["conducted_on"], unique=False
    )
    op.create_index(
        op.f("ix_quality_audit_created_at"), "quality_audit", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_quality_audit_created_by_id"), "quality_audit", ["created_by_id"], unique=False
    )
    op.create_index(
        op.f("ix_quality_audit_deleted_at"), "quality_audit", ["deleted_at"], unique=False
    )
    op.create_index(op.f("ix_quality_audit_kind"), "quality_audit", ["kind"], unique=False)
    op.create_index(
        "ix_quality_audit_open", "quality_audit", ["status", "next_review_due_on"], unique=False
    )
    op.create_index(
        op.f("ix_quality_audit_programme_id"), "quality_audit", ["programme_id"], unique=False
    )
    op.create_index(op.f("ix_quality_audit_status"), "quality_audit", ["status"], unique=False)
    op.create_index(op.f("ix_quality_audit_unit_id"), "quality_audit", ["unit_id"], unique=False)
    op.create_table(
        "quality_indicator",
        sa.Column("code", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("unit_id", sa.UUID(), nullable=True),
        sa.Column("programme_id", sa.UUID(), nullable=True),
        sa.Column("academic_year_id", sa.UUID(), nullable=True),
        sa.Column("semester_id", sa.UUID(), nullable=True),
        sa.Column("value", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column("unit_of_measure", sa.String(length=20), nullable=True),
        sa.Column("target", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("performance", sa.String(length=10), nullable=True),
        sa.Column("method_note", sa.Text(), nullable=True),
        sa.Column("numerator", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("denominator", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("computed_by_id", sa.UUID(), nullable=True),
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
            name=op.f("fk_quality_indicator_academic_year_id_academic_year"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["programme_id"],
            ["programme.id"],
            name=op.f("fk_quality_indicator_programme_id_programme"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["semester_id"],
            ["semester.id"],
            name=op.f("fk_quality_indicator_semester_id_semester"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["unit_id"],
            ["academic_unit.id"],
            name=op.f("fk_quality_indicator_unit_id_academic_unit"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quality_indicator")),
    )
    op.create_index(
        "ix_indicator_scope",
        "quality_indicator",
        ["code", "academic_year_id", "unit_id", "programme_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_quality_indicator_academic_year_id"),
        "quality_indicator",
        ["academic_year_id"],
        unique=False,
    )
    op.create_index(op.f("ix_quality_indicator_code"), "quality_indicator", ["code"], unique=False)
    op.create_index(
        op.f("ix_quality_indicator_created_at"), "quality_indicator", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_quality_indicator_created_by_id"),
        "quality_indicator",
        ["created_by_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_quality_indicator_deleted_at"), "quality_indicator", ["deleted_at"], unique=False
    )
    op.create_index(
        op.f("ix_quality_indicator_performance"), "quality_indicator", ["performance"], unique=False
    )
    op.create_index(
        op.f("ix_quality_indicator_programme_id"),
        "quality_indicator",
        ["programme_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_quality_indicator_unit_id"), "quality_indicator", ["unit_id"], unique=False
    )
    op.create_table(
        "institution_transfer",
        sa.Column("reference", sa.String(length=40), nullable=False),
        sa.Column("direction", sa.String(length=10), nullable=False),
        sa.Column("student_id", sa.UUID(), nullable=True),
        sa.Column("applicant_id", sa.UUID(), nullable=True),
        sa.Column("other_institution_name", sa.String(length=200), nullable=False),
        sa.Column("other_institution_country", sa.String(length=2), nullable=False),
        sa.Column("other_institution_regulator_code", sa.String(length=40), nullable=True),
        sa.Column("other_programme_name", sa.String(length=200), nullable=True),
        sa.Column("programme_id", sa.UUID(), nullable=True),
        sa.Column("curriculum_version_id", sa.UUID(), nullable=True),
        sa.Column("effective_semester_id", sa.UUID(), nullable=True),
        sa.Column("entry_year_of_study", sa.Integer(), nullable=True),
        sa.Column("credit_assessment", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("credits_claimed", sa.Integer(), nullable=False),
        sa.Column("credits_awarded", sa.Integer(), nullable=False),
        sa.Column("credit_transfer_cap_percent", sa.Integer(), nullable=True),
        sa.Column("evidence_attachment_ids", postgresql.ARRAY(sa.UUID()), nullable=False),
        sa.Column("transcript_issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("letter_issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assessed_by_id", sa.UUID(), nullable=True),
        sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by_id", sa.UUID(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("senate_minute_reference", sa.String(length=80), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
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
            "direction IN ('incoming', 'outgoing')",
            name=op.f("ck_institution_transfer_ck_transfer_direction"),
        ),
        sa.ForeignKeyConstraint(
            ["curriculum_version_id"],
            ["curriculum_version.id"],
            name=op.f("fk_institution_transfer_curriculum_version_id_curriculum_version"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["effective_semester_id"],
            ["semester.id"],
            name=op.f("fk_institution_transfer_effective_semester_id_semester"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["programme_id"],
            ["programme.id"],
            name=op.f("fk_institution_transfer_programme_id_programme"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["student.id"],
            name=op.f("fk_institution_transfer_student_id_student"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_institution_transfer")),
        sa.UniqueConstraint("reference", name=op.f("uq_institution_transfer_reference")),
    )
    op.create_index(
        op.f("ix_institution_transfer_applicant_id"),
        "institution_transfer",
        ["applicant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_institution_transfer_created_at"),
        "institution_transfer",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_institution_transfer_created_by_id"),
        "institution_transfer",
        ["created_by_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_institution_transfer_deleted_at"),
        "institution_transfer",
        ["deleted_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_institution_transfer_direction"),
        "institution_transfer",
        ["direction"],
        unique=False,
    )
    op.create_index(
        "ix_institution_transfer_queue",
        "institution_transfer",
        ["direction", "status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_institution_transfer_status"), "institution_transfer", ["status"], unique=False
    )
    op.create_index(
        op.f("ix_institution_transfer_student_id"),
        "institution_transfer",
        ["student_id"],
        unique=False,
    )
    op.create_table(
        "library_member",
        sa.Column("membership_number", sa.String(length=40), nullable=False),
        sa.Column("student_id", sa.UUID(), nullable=True),
        sa.Column("staff_id", sa.UUID(), nullable=True),
        sa.Column("full_name", sa.String(length=200), nullable=True),
        sa.Column("email", sa.String(length=200), nullable=True),
        sa.Column("phone", sa.String(length=40), nullable=True),
        sa.Column("borrower_category", sa.String(length=30), nullable=False),
        sa.Column("home_library_id", sa.UUID(), nullable=True),
        sa.Column("joined_on", sa.Date(), nullable=False),
        sa.Column("expires_on", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("suspension_reason", sa.String(length=300), nullable=True),
        sa.Column("outstanding_fines_minor", sa.Integer(), nullable=False),
        sa.Column("fines_recomputed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("items_on_loan", sa.Integer(), nullable=False),
        sa.Column("cleared_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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
            "student_id IS NOT NULL OR staff_id IS NOT NULL OR full_name IS NOT NULL",
            name=op.f("ck_library_member_ck_member_identified"),
        ),
        sa.ForeignKeyConstraint(
            ["home_library_id"],
            ["library.id"],
            name=op.f("fk_library_member_home_library_id_library"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["staff_id"],
            ["staff.id"],
            name=op.f("fk_library_member_staff_id_staff"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["student.id"],
            name=op.f("fk_library_member_student_id_student"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_library_member")),
    )
    op.create_index(
        op.f("ix_library_member_borrower_category"),
        "library_member",
        ["borrower_category"],
        unique=False,
    )
    op.create_index(
        op.f("ix_library_member_created_at"), "library_member", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_library_member_created_by_id"), "library_member", ["created_by_id"], unique=False
    )
    op.create_index(
        op.f("ix_library_member_deleted_at"), "library_member", ["deleted_at"], unique=False
    )
    op.create_index(
        op.f("ix_library_member_expires_on"), "library_member", ["expires_on"], unique=False
    )
    op.create_index(
        op.f("ix_library_member_membership_number"),
        "library_member",
        ["membership_number"],
        unique=True,
    )
    op.create_index(
        op.f("ix_library_member_staff_id"), "library_member", ["staff_id"], unique=False
    )
    op.create_index(op.f("ix_library_member_status"), "library_member", ["status"], unique=False)
    op.create_index(
        op.f("ix_library_member_student_id"), "library_member", ["student_id"], unique=False
    )
    op.create_index("ix_member_person", "library_member", ["student_id", "staff_id"], unique=False)
    op.create_table(
        "dunning_notice",
        sa.Column("student_id", sa.UUID(), nullable=False),
        sa.Column("invoice_id", sa.UUID(), nullable=True),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("sent_on", sa.Date(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("balance_minor", sa.Integer(), nullable=False),
        sa.Column("days_overdue", sa.Integer(), nullable=False),
        sa.Column("consequence_stated", sa.String(length=300), nullable=True),
        sa.Column("sent_to_sponsor", sa.Boolean(), nullable=False),
        sa.Column("recipient", sa.String(length=200), nullable=True),
        sa.Column("delivered", sa.Boolean(), nullable=True),
        sa.Column("delivery_note", sa.String(length=300), nullable=True),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("response_note", sa.Text(), nullable=True),
        sa.Column("sent_by_id", sa.UUID(), nullable=True),
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
            ["invoice_id"],
            ["invoice.id"],
            name=op.f("fk_dunning_notice_invoice_id_invoice"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["student.id"],
            name=op.f("fk_dunning_notice_student_id_student"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dunning_notice")),
    )
    op.create_index(
        "ix_dunning_ladder", "dunning_notice", ["student_id", "level", "sent_on"], unique=False
    )
    op.create_index(
        op.f("ix_dunning_notice_created_at"), "dunning_notice", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_dunning_notice_created_by_id"), "dunning_notice", ["created_by_id"], unique=False
    )
    op.create_index(
        op.f("ix_dunning_notice_deleted_at"), "dunning_notice", ["deleted_at"], unique=False
    )
    op.create_index(
        op.f("ix_dunning_notice_invoice_id"), "dunning_notice", ["invoice_id"], unique=False
    )
    op.create_index(op.f("ix_dunning_notice_level"), "dunning_notice", ["level"], unique=False)
    op.create_index(op.f("ix_dunning_notice_sent_on"), "dunning_notice", ["sent_on"], unique=False)
    op.create_index(
        op.f("ix_dunning_notice_student_id"), "dunning_notice", ["student_id"], unique=False
    )
    op.create_table(
        "library_loan",
        sa.Column("copy_id", sa.UUID(), nullable=False),
        sa.Column("member_id", sa.UUID(), nullable=False),
        sa.Column("library_id", sa.UUID(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("issued_by_id", sa.UUID(), nullable=True),
        sa.Column("due_on", sa.Date(), nullable=False),
        sa.Column("original_due_on", sa.Date(), nullable=False),
        sa.Column("returned_on", sa.Date(), nullable=True),
        sa.Column("returned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_by_id", sa.UUID(), nullable=True),
        sa.Column("renewals", sa.Integer(), nullable=False),
        sa.Column("recalled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("return_condition", sa.String(length=20), nullable=True),
        sa.Column("fine_per_day_minor", sa.Integer(), nullable=False),
        sa.Column("notices_sent", sa.Integer(), nullable=False),
        sa.Column("last_notice_on", sa.Date(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
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
            ["copy_id"],
            ["catalogue_copy.id"],
            name=op.f("fk_library_loan_copy_id_catalogue_copy"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["library_id"],
            ["library.id"],
            name=op.f("fk_library_loan_library_id_library"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["member_id"],
            ["library_member.id"],
            name=op.f("fk_library_loan_member_id_library_member"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_library_loan")),
    )
    op.create_index(op.f("ix_library_loan_copy_id"), "library_loan", ["copy_id"], unique=False)
    op.create_index(
        op.f("ix_library_loan_created_at"), "library_loan", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_library_loan_created_by_id"), "library_loan", ["created_by_id"], unique=False
    )
    op.create_index(
        op.f("ix_library_loan_deleted_at"), "library_loan", ["deleted_at"], unique=False
    )
    op.create_index(op.f("ix_library_loan_due_on"), "library_loan", ["due_on"], unique=False)
    op.create_index(
        op.f("ix_library_loan_library_id"), "library_loan", ["library_id"], unique=False
    )
    op.create_index(op.f("ix_library_loan_member_id"), "library_loan", ["member_id"], unique=False)
    op.create_index(
        op.f("ix_library_loan_returned_on"), "library_loan", ["returned_on"], unique=False
    )
    op.create_index(op.f("ix_library_loan_status"), "library_loan", ["status"], unique=False)
    op.create_index("ix_loan_member_open", "library_loan", ["member_id", "status"], unique=False)
    op.create_index("ix_loan_open", "library_loan", ["status", "due_on"], unique=False)
    op.create_table(
        "library_reservation",
        sa.Column("record_id", sa.UUID(), nullable=False),
        sa.Column("member_id", sa.UUID(), nullable=False),
        sa.Column("library_id", sa.UUID(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("queue_position", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("allocated_copy_id", sa.UUID(), nullable=True),
        sa.Column("allocated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("collect_by", sa.Date(), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
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
            ["allocated_copy_id"],
            ["catalogue_copy.id"],
            name=op.f("fk_library_reservation_allocated_copy_id_catalogue_copy"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["library_id"],
            ["library.id"],
            name=op.f("fk_library_reservation_library_id_library"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["member_id"],
            ["library_member.id"],
            name=op.f("fk_library_reservation_member_id_library_member"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["record_id"],
            ["catalogue_record.id"],
            name=op.f("fk_library_reservation_record_id_catalogue_record"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_library_reservation")),
        sa.UniqueConstraint("record_id", "member_id", "status", name="uq_reservation_once"),
    )
    op.create_index(
        op.f("ix_library_reservation_collect_by"),
        "library_reservation",
        ["collect_by"],
        unique=False,
    )
    op.create_index(
        op.f("ix_library_reservation_created_at"),
        "library_reservation",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_library_reservation_created_by_id"),
        "library_reservation",
        ["created_by_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_library_reservation_deleted_at"),
        "library_reservation",
        ["deleted_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_library_reservation_member_id"), "library_reservation", ["member_id"], unique=False
    )
    op.create_index(
        op.f("ix_library_reservation_record_id"), "library_reservation", ["record_id"], unique=False
    )
    op.create_index(
        op.f("ix_library_reservation_status"), "library_reservation", ["status"], unique=False
    )
    op.create_table(
        "payment_plan",
        sa.Column("reference", sa.String(length=40), nullable=False),
        sa.Column("student_id", sa.UUID(), nullable=False),
        sa.Column("invoice_id", sa.UUID(), nullable=True),
        sa.Column("semester_id", sa.UUID(), nullable=True),
        sa.Column("total_minor", sa.Integer(), nullable=False),
        sa.Column("deposit_minor", sa.Integer(), nullable=False),
        sa.Column("instalment_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_by_id", sa.UUID(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decline_reason", sa.Text(), nullable=True),
        sa.Column("missed_allowance", sa.Integer(), nullable=False),
        sa.Column("missed_count", sa.Integer(), nullable=False),
        sa.Column("defaulted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("agreement_attachment_id", sa.UUID(), nullable=True),
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
            "instalment_count >= 1", name=op.f("ck_payment_plan_ck_plan_instalments")
        ),
        sa.ForeignKeyConstraint(
            ["invoice_id"],
            ["invoice.id"],
            name=op.f("fk_payment_plan_invoice_id_invoice"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["semester_id"],
            ["semester.id"],
            name=op.f("fk_payment_plan_semester_id_semester"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["student.id"],
            name=op.f("fk_payment_plan_student_id_student"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payment_plan")),
        sa.UniqueConstraint("reference", name=op.f("uq_payment_plan_reference")),
    )
    op.create_index(
        op.f("ix_payment_plan_created_at"), "payment_plan", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_payment_plan_created_by_id"), "payment_plan", ["created_by_id"], unique=False
    )
    op.create_index(
        op.f("ix_payment_plan_deleted_at"), "payment_plan", ["deleted_at"], unique=False
    )
    op.create_index(
        op.f("ix_payment_plan_invoice_id"), "payment_plan", ["invoice_id"], unique=False
    )
    op.create_index(
        op.f("ix_payment_plan_semester_id"), "payment_plan", ["semester_id"], unique=False
    )
    op.create_index(op.f("ix_payment_plan_status"), "payment_plan", ["status"], unique=False)
    op.create_index(
        op.f("ix_payment_plan_student_id"), "payment_plan", ["student_id"], unique=False
    )
    op.create_table(
        "penalty_charge",
        sa.Column("student_id", sa.UUID(), nullable=False),
        sa.Column("invoice_id", sa.UUID(), nullable=False),
        sa.Column("rule_id", sa.UUID(), nullable=True),
        sa.Column("invoice_line_id", sa.UUID(), nullable=True),
        sa.Column("charged_on", sa.Date(), nullable=False),
        sa.Column("days_overdue", sa.Integer(), nullable=False),
        sa.Column("balance_at_charge_minor", sa.Integer(), nullable=False),
        sa.Column("percent_applied", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("applied_by_id", sa.UUID(), nullable=True),
        sa.Column("applied_automatically", sa.Boolean(), nullable=False),
        sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reversed_by_id", sa.UUID(), nullable=True),
        sa.Column("reversal_reason", sa.Text(), nullable=True),
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
            ["invoice_id"],
            ["invoice.id"],
            name=op.f("fk_penalty_charge_invoice_id_invoice"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["rule_id"],
            ["late_payment_rule.id"],
            name=op.f("fk_penalty_charge_rule_id_late_payment_rule"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["student.id"],
            name=op.f("fk_penalty_charge_student_id_student"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_penalty_charge")),
        sa.UniqueConstraint("invoice_id", "rule_id", "sequence", name="uq_penalty_sequence"),
    )
    op.create_index(
        op.f("ix_penalty_charge_charged_on"), "penalty_charge", ["charged_on"], unique=False
    )
    op.create_index(
        op.f("ix_penalty_charge_created_at"), "penalty_charge", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_penalty_charge_created_by_id"), "penalty_charge", ["created_by_id"], unique=False
    )
    op.create_index(
        op.f("ix_penalty_charge_deleted_at"), "penalty_charge", ["deleted_at"], unique=False
    )
    op.create_index(
        op.f("ix_penalty_charge_invoice_id"), "penalty_charge", ["invoice_id"], unique=False
    )
    op.create_index(op.f("ix_penalty_charge_status"), "penalty_charge", ["status"], unique=False)
    op.create_index(
        op.f("ix_penalty_charge_student_id"), "penalty_charge", ["student_id"], unique=False
    )
    op.create_table(
        "course_evaluation",
        sa.Column("instrument_id", sa.UUID(), nullable=False),
        sa.Column("course_offering_id", sa.UUID(), nullable=False),
        sa.Column("semester_id", sa.UUID(), nullable=False),
        sa.Column("staff_id", sa.UUID(), nullable=True),
        sa.Column("opens_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closes_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("results_visible_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("invited_count", sa.Integer(), nullable=False),
        sa.Column("response_count", sa.Integer(), nullable=False),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_reportable", sa.Boolean(), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("staff_reflection", sa.Text(), nullable=True),
        sa.Column("reflection_submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("action_plan", sa.Text(), nullable=True),
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
            "closes_at > opens_at", name=op.f("ck_course_evaluation_ck_evaluation_window")
        ),
        sa.ForeignKeyConstraint(
            ["course_offering_id"],
            ["course_offering.id"],
            name=op.f("fk_course_evaluation_course_offering_id_course_offering"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["evaluation_instrument.id"],
            name=op.f("fk_course_evaluation_instrument_id_evaluation_instrument"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["semester_id"],
            ["semester.id"],
            name=op.f("fk_course_evaluation_semester_id_semester"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["staff_id"],
            ["staff.id"],
            name=op.f("fk_course_evaluation_staff_id_staff"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_course_evaluation")),
        sa.UniqueConstraint(
            "course_offering_id", "instrument_id", "staff_id", name="uq_course_evaluation"
        ),
    )
    op.create_index(
        op.f("ix_course_evaluation_course_offering_id"),
        "course_evaluation",
        ["course_offering_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_course_evaluation_created_at"), "course_evaluation", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_course_evaluation_created_by_id"),
        "course_evaluation",
        ["created_by_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_course_evaluation_deleted_at"), "course_evaluation", ["deleted_at"], unique=False
    )
    op.create_index(
        op.f("ix_course_evaluation_instrument_id"),
        "course_evaluation",
        ["instrument_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_course_evaluation_semester_id"), "course_evaluation", ["semester_id"], unique=False
    )
    op.create_index(
        op.f("ix_course_evaluation_staff_id"), "course_evaluation", ["staff_id"], unique=False
    )
    op.create_index(
        op.f("ix_course_evaluation_status"), "course_evaluation", ["status"], unique=False
    )
    op.create_table(
        "library_fine",
        sa.Column("member_id", sa.UUID(), nullable=False),
        sa.Column("loan_id", sa.UUID(), nullable=True),
        sa.Column("copy_id", sa.UUID(), nullable=True),
        sa.Column("reason", sa.String(length=30), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("days_overdue", sa.Integer(), nullable=True),
        sa.Column("rate_per_day_minor", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("raised_on", sa.Date(), nullable=False),
        sa.Column("raised_by_id", sa.UUID(), nullable=True),
        sa.Column("invoice_id", sa.UUID(), nullable=True),
        sa.Column("settled_on", sa.Date(), nullable=True),
        sa.Column("waived_by_id", sa.UUID(), nullable=True),
        sa.Column("waiver_reason", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
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
            ["copy_id"],
            ["catalogue_copy.id"],
            name=op.f("fk_library_fine_copy_id_catalogue_copy"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["loan_id"],
            ["library_loan.id"],
            name=op.f("fk_library_fine_loan_id_library_loan"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["member_id"],
            ["library_member.id"],
            name=op.f("fk_library_fine_member_id_library_member"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_library_fine")),
    )
    op.create_index(
        op.f("ix_library_fine_created_at"), "library_fine", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_library_fine_created_by_id"), "library_fine", ["created_by_id"], unique=False
    )
    op.create_index(
        op.f("ix_library_fine_deleted_at"), "library_fine", ["deleted_at"], unique=False
    )
    op.create_index(
        op.f("ix_library_fine_invoice_id"), "library_fine", ["invoice_id"], unique=False
    )
    op.create_index(op.f("ix_library_fine_loan_id"), "library_fine", ["loan_id"], unique=False)
    op.create_index(op.f("ix_library_fine_member_id"), "library_fine", ["member_id"], unique=False)
    op.create_index(op.f("ix_library_fine_raised_on"), "library_fine", ["raised_on"], unique=False)
    op.create_index(op.f("ix_library_fine_reason"), "library_fine", ["reason"], unique=False)
    op.create_index(op.f("ix_library_fine_status"), "library_fine", ["status"], unique=False)
    op.create_table(
        "payment_plan_instalment",
        sa.Column("plan_id", sa.UUID(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("due_on", sa.Date(), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("paid_minor", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("settled_on", sa.Date(), nullable=True),
        sa.Column("payment_ids", postgresql.ARRAY(sa.UUID()), nullable=False),
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
            ["plan_id"],
            ["payment_plan.id"],
            name=op.f("fk_payment_plan_instalment_plan_id_payment_plan"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payment_plan_instalment")),
        sa.UniqueConstraint("plan_id", "sequence", name="uq_instalment_sequence"),
    )
    op.create_index(
        op.f("ix_payment_plan_instalment_created_at"),
        "payment_plan_instalment",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_payment_plan_instalment_created_by_id"),
        "payment_plan_instalment",
        ["created_by_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_payment_plan_instalment_deleted_at"),
        "payment_plan_instalment",
        ["deleted_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_payment_plan_instalment_due_on"),
        "payment_plan_instalment",
        ["due_on"],
        unique=False,
    )
    op.create_index(
        op.f("ix_payment_plan_instalment_plan_id"),
        "payment_plan_instalment",
        ["plan_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_payment_plan_instalment_status"),
        "payment_plan_instalment",
        ["status"],
        unique=False,
    )
    op.create_table(
        "special_exam_request",
        sa.Column("reference", sa.String(length=40), nullable=False),
        sa.Column("student_id", sa.UUID(), nullable=False),
        sa.Column("course_offering_id", sa.UUID(), nullable=False),
        sa.Column("semester_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("ground", sa.String(length=30), nullable=False),
        sa.Column("narrative", sa.Text(), nullable=False),
        sa.Column("missed_on", sa.Date(), nullable=True),
        sa.Column("evidence_attachment_ids", postgresql.ARRAY(sa.UUID()), nullable=False),
        sa.Column("evidence_verified_by_id", sa.UUID(), nullable=True),
        sa.Column("evidence_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fee_minor", sa.Integer(), nullable=True),
        sa.Column("fee_invoice_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recommended_by_id", sa.UUID(), nullable=True),
        sa.Column("recommended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by_id", sa.UUID(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("minute_reference", sa.String(length=80), nullable=True),
        sa.Column("exam_sitting_id", sa.UUID(), nullable=True),
        sa.Column("mark_recorded", sa.Boolean(), nullable=False),
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
            ["course_offering_id"],
            ["course_offering.id"],
            name=op.f("fk_special_exam_request_course_offering_id_course_offering"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["semester_id"],
            ["semester.id"],
            name=op.f("fk_special_exam_request_semester_id_semester"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["student.id"],
            name=op.f("fk_special_exam_request_student_id_student"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_special_exam_request")),
        sa.UniqueConstraint(
            "student_id", "course_offering_id", "kind", name="uq_special_exam_request"
        ),
    )
    op.create_index(
        "ix_special_exam_queue", "special_exam_request", ["status", "semester_id"], unique=False
    )
    op.create_index(
        op.f("ix_special_exam_request_course_offering_id"),
        "special_exam_request",
        ["course_offering_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_special_exam_request_created_at"),
        "special_exam_request",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_special_exam_request_created_by_id"),
        "special_exam_request",
        ["created_by_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_special_exam_request_deleted_at"),
        "special_exam_request",
        ["deleted_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_special_exam_request_exam_sitting_id"),
        "special_exam_request",
        ["exam_sitting_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_special_exam_request_kind"), "special_exam_request", ["kind"], unique=False
    )
    op.create_index(
        op.f("ix_special_exam_request_reference"),
        "special_exam_request",
        ["reference"],
        unique=True,
    )
    op.create_index(
        op.f("ix_special_exam_request_semester_id"),
        "special_exam_request",
        ["semester_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_special_exam_request_status"), "special_exam_request", ["status"], unique=False
    )
    op.create_index(
        op.f("ix_special_exam_request_student_id"),
        "special_exam_request",
        ["student_id"],
        unique=False,
    )
    op.create_table(
        "class_session",
        sa.Column("course_offering_id", sa.UUID(), nullable=False),
        sa.Column("semester_id", sa.UUID(), nullable=False),
        sa.Column("timetable_slot_id", sa.UUID(), nullable=True),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("starts_at", sa.String(length=5), nullable=False),
        sa.Column("ends_at", sa.String(length=5), nullable=False),
        sa.Column("week_number", sa.Integer(), nullable=True),
        sa.Column("room_id", sa.UUID(), nullable=True),
        sa.Column("scheduled_staff_id", sa.UUID(), nullable=True),
        sa.Column("delivered_by_staff_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("topic", sa.String(length=300), nullable=True),
        sa.Column("syllabus_reference", sa.String(length=120), nullable=True),
        sa.Column("cancellation_reason", sa.String(length=300), nullable=True),
        sa.Column("rescheduled_to_session_id", sa.UUID(), nullable=True),
        sa.Column("register_closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("register_closed_by_id", sa.UUID(), nullable=True),
        sa.Column("expected_students", sa.Integer(), nullable=False),
        sa.Column("present_count", sa.Integer(), nullable=False),
        sa.Column("attendance_percent", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
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
            ["course_offering_id"],
            ["course_offering.id"],
            name=op.f("fk_class_session_course_offering_id_course_offering"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["delivered_by_staff_id"],
            ["staff.id"],
            name=op.f("fk_class_session_delivered_by_staff_id_staff"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["room_id"],
            ["room.id"],
            name=op.f("fk_class_session_room_id_room"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["scheduled_staff_id"],
            ["staff.id"],
            name=op.f("fk_class_session_scheduled_staff_id_staff"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["semester_id"],
            ["semester.id"],
            name=op.f("fk_class_session_semester_id_semester"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["timetable_slot_id"],
            ["timetable_slot.id"],
            name=op.f("fk_class_session_timetable_slot_id_timetable_slot"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_class_session")),
        sa.UniqueConstraint(
            "course_offering_id", "session_date", "starts_at", name="uq_class_session"
        ),
    )
    op.create_index(
        op.f("ix_class_session_course_offering_id"),
        "class_session",
        ["course_offering_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_class_session_created_at"), "class_session", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_class_session_created_by_id"), "class_session", ["created_by_id"], unique=False
    )
    op.create_index(
        op.f("ix_class_session_deleted_at"), "class_session", ["deleted_at"], unique=False
    )
    op.create_index(
        op.f("ix_class_session_delivered_by_staff_id"),
        "class_session",
        ["delivered_by_staff_id"],
        unique=False,
    )
    op.create_index(
        "ix_class_session_delivery", "class_session", ["semester_id", "status"], unique=False
    )
    op.create_index(
        op.f("ix_class_session_scheduled_staff_id"),
        "class_session",
        ["scheduled_staff_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_class_session_semester_id"), "class_session", ["semester_id"], unique=False
    )
    op.create_index(
        op.f("ix_class_session_session_date"), "class_session", ["session_date"], unique=False
    )
    op.create_index(op.f("ix_class_session_status"), "class_session", ["status"], unique=False)
    op.create_index(
        op.f("ix_class_session_week_number"), "class_session", ["week_number"], unique=False
    )
    op.create_table(
        "evaluation_invitation",
        sa.Column("evaluation_id", sa.UUID(), nullable=False),
        sa.Column("student_id", sa.UUID(), nullable=False),
        sa.Column("invited_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reminders_sent", sa.Integer(), nullable=False),
        sa.Column("last_reminder_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("declined_at", sa.DateTime(timezone=True), nullable=True),
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
            ["evaluation_id"],
            ["course_evaluation.id"],
            name=op.f("fk_evaluation_invitation_evaluation_id_course_evaluation"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["student.id"],
            name=op.f("fk_evaluation_invitation_student_id_student"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evaluation_invitation")),
        sa.UniqueConstraint("evaluation_id", "student_id", name="uq_evaluation_invitation"),
    )
    op.create_index(
        op.f("ix_evaluation_invitation_created_at"),
        "evaluation_invitation",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_evaluation_invitation_created_by_id"),
        "evaluation_invitation",
        ["created_by_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_evaluation_invitation_deleted_at"),
        "evaluation_invitation",
        ["deleted_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_evaluation_invitation_evaluation_id"),
        "evaluation_invitation",
        ["evaluation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_evaluation_invitation_student_id"),
        "evaluation_invitation",
        ["student_id"],
        unique=False,
    )
    op.create_table(
        "evaluation_response",
        sa.Column("evaluation_id", sa.UUID(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("answers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("comments", sa.Text(), nullable=True),
        sa.Column("year_of_study", sa.Integer(), nullable=True),
        sa.Column("study_mode", sa.String(length=20), nullable=True),
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
            ["evaluation_id"],
            ["course_evaluation.id"],
            name=op.f("fk_evaluation_response_evaluation_id_course_evaluation"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evaluation_response")),
    )
    op.create_index(
        op.f("ix_evaluation_response_created_at"),
        "evaluation_response",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_evaluation_response_created_by_id"),
        "evaluation_response",
        ["created_by_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_evaluation_response_deleted_at"),
        "evaluation_response",
        ["deleted_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_evaluation_response_evaluation_id"),
        "evaluation_response",
        ["evaluation_id"],
        unique=False,
    )
    op.create_table(
        "exam_card",
        sa.Column("student_id", sa.UUID(), nullable=False),
        sa.Column("registration_id", sa.UUID(), nullable=False),
        sa.Column("semester_id", sa.UUID(), nullable=False),
        sa.Column("verification_code", sa.String(length=40), nullable=False),
        sa.Column("session", sa.String(length=20), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("issued_by_id", sa.UUID(), nullable=True),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("course_offering_ids", postgresql.ARRAY(sa.UUID()), nullable=False),
        sa.Column("clearance_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("override_reason", sa.Text(), nullable=True),
        sa.Column("overridden_by_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.Text(), nullable=True),
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
            ["registration_id"],
            ["registration.id"],
            name=op.f("fk_exam_card_registration_id_registration"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["semester_id"],
            ["semester.id"],
            name=op.f("fk_exam_card_semester_id_semester"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["student.id"],
            name=op.f("fk_exam_card_student_id_student"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_exam_card")),
        sa.UniqueConstraint("registration_id", "session", name="uq_exam_card_registration"),
    )
    op.create_index(op.f("ix_exam_card_created_at"), "exam_card", ["created_at"], unique=False)
    op.create_index(
        op.f("ix_exam_card_created_by_id"), "exam_card", ["created_by_id"], unique=False
    )
    op.create_index(op.f("ix_exam_card_deleted_at"), "exam_card", ["deleted_at"], unique=False)
    op.create_index(
        op.f("ix_exam_card_registration_id"), "exam_card", ["registration_id"], unique=False
    )
    op.create_index(op.f("ix_exam_card_semester_id"), "exam_card", ["semester_id"], unique=False)
    op.create_index(op.f("ix_exam_card_status"), "exam_card", ["status"], unique=False)
    op.create_index(op.f("ix_exam_card_student_id"), "exam_card", ["student_id"], unique=False)
    op.create_index(
        op.f("ix_exam_card_verification_code"), "exam_card", ["verification_code"], unique=True
    )
    op.create_table(
        "session_attendance",
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("student_id", sa.UUID(), nullable=False),
        sa.Column("course_offering_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("method", sa.String(length=20), nullable=False),
        sa.Column("marked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("marked_by_id", sa.UUID(), nullable=True),
        sa.Column("minutes_late", sa.Integer(), nullable=True),
        sa.Column("excuse_reason", sa.String(length=300), nullable=True),
        sa.Column("excuse_attachment_id", sa.UUID(), nullable=True),
        sa.Column("excused_by_id", sa.UUID(), nullable=True),
        sa.Column("disputed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dispute_note", sa.Text(), nullable=True),
        sa.Column("resolved_by_id", sa.UUID(), nullable=True),
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
            ["course_offering_id"],
            ["course_offering.id"],
            name=op.f("fk_session_attendance_course_offering_id_course_offering"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["class_session.id"],
            name=op.f("fk_session_attendance_session_id_class_session"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["student.id"],
            name=op.f("fk_session_attendance_student_id_student"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_session_attendance")),
        sa.UniqueConstraint("session_id", "student_id", name="uq_session_attendance"),
    )
    op.create_index(
        "ix_attendance_student_offering",
        "session_attendance",
        ["student_id", "course_offering_id", "status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_session_attendance_course_offering_id"),
        "session_attendance",
        ["course_offering_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_session_attendance_created_at"), "session_attendance", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_session_attendance_created_by_id"),
        "session_attendance",
        ["created_by_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_session_attendance_deleted_at"), "session_attendance", ["deleted_at"], unique=False
    )
    op.create_index(
        op.f("ix_session_attendance_session_id"), "session_attendance", ["session_id"], unique=False
    )
    op.create_index(
        op.f("ix_session_attendance_status"), "session_attendance", ["status"], unique=False
    )
    op.create_index(
        op.f("ix_session_attendance_student_id"), "session_attendance", ["student_id"], unique=False
    )
    op.create_table(
        "staff_attendance",
        sa.Column("staff_id", sa.UUID(), nullable=False),
        sa.Column("attendance_date", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("class_session_id", sa.UUID(), nullable=True),
        sa.Column("exam_sitting_id", sa.UUID(), nullable=True),
        sa.Column("checked_in_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("checked_out_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("hours", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("payable", sa.Boolean(), nullable=False),
        sa.Column("payroll_period", sa.String(length=20), nullable=True),
        sa.Column("absence_reason", sa.String(length=300), nullable=True),
        sa.Column("leave_request_id", sa.UUID(), nullable=True),
        sa.Column("recorded_by_id", sa.UUID(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
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
            ["class_session_id"],
            ["class_session.id"],
            name=op.f("fk_staff_attendance_class_session_id_class_session"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["staff_id"],
            ["staff.id"],
            name=op.f("fk_staff_attendance_staff_id_staff"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_staff_attendance")),
    )
    op.create_index(
        op.f("ix_staff_attendance_attendance_date"),
        "staff_attendance",
        ["attendance_date"],
        unique=False,
    )
    op.create_index(
        op.f("ix_staff_attendance_class_session_id"),
        "staff_attendance",
        ["class_session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_staff_attendance_created_at"), "staff_attendance", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_staff_attendance_created_by_id"),
        "staff_attendance",
        ["created_by_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_staff_attendance_deleted_at"), "staff_attendance", ["deleted_at"], unique=False
    )
    op.create_index(
        op.f("ix_staff_attendance_payroll_period"),
        "staff_attendance",
        ["payroll_period"],
        unique=False,
    )
    op.create_index(
        "ix_staff_attendance_period",
        "staff_attendance",
        ["staff_id", "attendance_date"],
        unique=False,
    )
    op.create_index(
        op.f("ix_staff_attendance_staff_id"), "staff_attendance", ["staff_id"], unique=False
    )
    op.create_index(
        op.f("ix_staff_attendance_status"), "staff_attendance", ["status"], unique=False
    )
    op.create_table(
        "teaching_observation",
        sa.Column("staff_id", sa.UUID(), nullable=False),
        sa.Column("observer_staff_id", sa.UUID(), nullable=False),
        sa.Column("course_offering_id", sa.UUID(), nullable=True),
        sa.Column("class_session_id", sa.UUID(), nullable=True),
        sa.Column("observed_on", sa.Date(), nullable=False),
        sa.Column("purpose", sa.String(length=30), nullable=False),
        sa.Column("rubric_scores", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("overall_score", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("strengths", sa.Text(), nullable=True),
        sa.Column("areas_to_develop", sa.Text(), nullable=True),
        sa.Column("agreed_actions", sa.Text(), nullable=True),
        sa.Column("observee_response", sa.Text(), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_developmental", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("follow_up_due_on", sa.Date(), nullable=True),
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
            ["class_session_id"],
            ["class_session.id"],
            name=op.f("fk_teaching_observation_class_session_id_class_session"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["course_offering_id"],
            ["course_offering.id"],
            name=op.f("fk_teaching_observation_course_offering_id_course_offering"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["observer_staff_id"],
            ["staff.id"],
            name=op.f("fk_teaching_observation_observer_staff_id_staff"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["staff_id"],
            ["staff.id"],
            name=op.f("fk_teaching_observation_staff_id_staff"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_teaching_observation")),
    )
    op.create_index(
        op.f("ix_teaching_observation_course_offering_id"),
        "teaching_observation",
        ["course_offering_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_teaching_observation_created_at"),
        "teaching_observation",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_teaching_observation_created_by_id"),
        "teaching_observation",
        ["created_by_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_teaching_observation_deleted_at"),
        "teaching_observation",
        ["deleted_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_teaching_observation_observed_on"),
        "teaching_observation",
        ["observed_on"],
        unique=False,
    )
    op.create_index(
        op.f("ix_teaching_observation_observer_staff_id"),
        "teaching_observation",
        ["observer_staff_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_teaching_observation_staff_id"), "teaching_observation", ["staff_id"], unique=False
    )
    op.create_index(
        op.f("ix_teaching_observation_status"), "teaching_observation", ["status"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_teaching_observation_status"), table_name="teaching_observation")
    op.drop_index(op.f("ix_teaching_observation_staff_id"), table_name="teaching_observation")
    op.drop_index(
        op.f("ix_teaching_observation_observer_staff_id"), table_name="teaching_observation"
    )
    op.drop_index(op.f("ix_teaching_observation_observed_on"), table_name="teaching_observation")
    op.drop_index(op.f("ix_teaching_observation_deleted_at"), table_name="teaching_observation")
    op.drop_index(op.f("ix_teaching_observation_created_by_id"), table_name="teaching_observation")
    op.drop_index(op.f("ix_teaching_observation_created_at"), table_name="teaching_observation")
    op.drop_index(
        op.f("ix_teaching_observation_course_offering_id"), table_name="teaching_observation"
    )
    op.drop_table("teaching_observation")
    op.drop_index(op.f("ix_staff_attendance_status"), table_name="staff_attendance")
    op.drop_index(op.f("ix_staff_attendance_staff_id"), table_name="staff_attendance")
    op.drop_index("ix_staff_attendance_period", table_name="staff_attendance")
    op.drop_index(op.f("ix_staff_attendance_payroll_period"), table_name="staff_attendance")
    op.drop_index(op.f("ix_staff_attendance_deleted_at"), table_name="staff_attendance")
    op.drop_index(op.f("ix_staff_attendance_created_by_id"), table_name="staff_attendance")
    op.drop_index(op.f("ix_staff_attendance_created_at"), table_name="staff_attendance")
    op.drop_index(op.f("ix_staff_attendance_class_session_id"), table_name="staff_attendance")
    op.drop_index(op.f("ix_staff_attendance_attendance_date"), table_name="staff_attendance")
    op.drop_table("staff_attendance")
    op.drop_index(op.f("ix_session_attendance_student_id"), table_name="session_attendance")
    op.drop_index(op.f("ix_session_attendance_status"), table_name="session_attendance")
    op.drop_index(op.f("ix_session_attendance_session_id"), table_name="session_attendance")
    op.drop_index(op.f("ix_session_attendance_deleted_at"), table_name="session_attendance")
    op.drop_index(op.f("ix_session_attendance_created_by_id"), table_name="session_attendance")
    op.drop_index(op.f("ix_session_attendance_created_at"), table_name="session_attendance")
    op.drop_index(op.f("ix_session_attendance_course_offering_id"), table_name="session_attendance")
    op.drop_index("ix_attendance_student_offering", table_name="session_attendance")
    op.drop_table("session_attendance")
    op.drop_index(op.f("ix_exam_card_verification_code"), table_name="exam_card")
    op.drop_index(op.f("ix_exam_card_student_id"), table_name="exam_card")
    op.drop_index(op.f("ix_exam_card_status"), table_name="exam_card")
    op.drop_index(op.f("ix_exam_card_semester_id"), table_name="exam_card")
    op.drop_index(op.f("ix_exam_card_registration_id"), table_name="exam_card")
    op.drop_index(op.f("ix_exam_card_deleted_at"), table_name="exam_card")
    op.drop_index(op.f("ix_exam_card_created_by_id"), table_name="exam_card")
    op.drop_index(op.f("ix_exam_card_created_at"), table_name="exam_card")
    op.drop_table("exam_card")
    op.drop_index(op.f("ix_evaluation_response_evaluation_id"), table_name="evaluation_response")
    op.drop_index(op.f("ix_evaluation_response_deleted_at"), table_name="evaluation_response")
    op.drop_index(op.f("ix_evaluation_response_created_by_id"), table_name="evaluation_response")
    op.drop_index(op.f("ix_evaluation_response_created_at"), table_name="evaluation_response")
    op.drop_table("evaluation_response")
    op.drop_index(op.f("ix_evaluation_invitation_student_id"), table_name="evaluation_invitation")
    op.drop_index(
        op.f("ix_evaluation_invitation_evaluation_id"), table_name="evaluation_invitation"
    )
    op.drop_index(op.f("ix_evaluation_invitation_deleted_at"), table_name="evaluation_invitation")
    op.drop_index(
        op.f("ix_evaluation_invitation_created_by_id"), table_name="evaluation_invitation"
    )
    op.drop_index(op.f("ix_evaluation_invitation_created_at"), table_name="evaluation_invitation")
    op.drop_table("evaluation_invitation")
    op.drop_index(op.f("ix_class_session_week_number"), table_name="class_session")
    op.drop_index(op.f("ix_class_session_status"), table_name="class_session")
    op.drop_index(op.f("ix_class_session_session_date"), table_name="class_session")
    op.drop_index(op.f("ix_class_session_semester_id"), table_name="class_session")
    op.drop_index(op.f("ix_class_session_scheduled_staff_id"), table_name="class_session")
    op.drop_index("ix_class_session_delivery", table_name="class_session")
    op.drop_index(op.f("ix_class_session_delivered_by_staff_id"), table_name="class_session")
    op.drop_index(op.f("ix_class_session_deleted_at"), table_name="class_session")
    op.drop_index(op.f("ix_class_session_created_by_id"), table_name="class_session")
    op.drop_index(op.f("ix_class_session_created_at"), table_name="class_session")
    op.drop_index(op.f("ix_class_session_course_offering_id"), table_name="class_session")
    op.drop_table("class_session")
    op.drop_index(op.f("ix_special_exam_request_student_id"), table_name="special_exam_request")
    op.drop_index(op.f("ix_special_exam_request_status"), table_name="special_exam_request")
    op.drop_index(op.f("ix_special_exam_request_semester_id"), table_name="special_exam_request")
    op.drop_index(op.f("ix_special_exam_request_reference"), table_name="special_exam_request")
    op.drop_index(op.f("ix_special_exam_request_kind"), table_name="special_exam_request")
    op.drop_index(
        op.f("ix_special_exam_request_exam_sitting_id"), table_name="special_exam_request"
    )
    op.drop_index(op.f("ix_special_exam_request_deleted_at"), table_name="special_exam_request")
    op.drop_index(op.f("ix_special_exam_request_created_by_id"), table_name="special_exam_request")
    op.drop_index(op.f("ix_special_exam_request_created_at"), table_name="special_exam_request")
    op.drop_index(
        op.f("ix_special_exam_request_course_offering_id"), table_name="special_exam_request"
    )
    op.drop_index("ix_special_exam_queue", table_name="special_exam_request")
    op.drop_table("special_exam_request")
    op.drop_index(op.f("ix_payment_plan_instalment_status"), table_name="payment_plan_instalment")
    op.drop_index(op.f("ix_payment_plan_instalment_plan_id"), table_name="payment_plan_instalment")
    op.drop_index(op.f("ix_payment_plan_instalment_due_on"), table_name="payment_plan_instalment")
    op.drop_index(
        op.f("ix_payment_plan_instalment_deleted_at"), table_name="payment_plan_instalment"
    )
    op.drop_index(
        op.f("ix_payment_plan_instalment_created_by_id"), table_name="payment_plan_instalment"
    )
    op.drop_index(
        op.f("ix_payment_plan_instalment_created_at"), table_name="payment_plan_instalment"
    )
    op.drop_table("payment_plan_instalment")
    op.drop_index(op.f("ix_library_fine_status"), table_name="library_fine")
    op.drop_index(op.f("ix_library_fine_reason"), table_name="library_fine")
    op.drop_index(op.f("ix_library_fine_raised_on"), table_name="library_fine")
    op.drop_index(op.f("ix_library_fine_member_id"), table_name="library_fine")
    op.drop_index(op.f("ix_library_fine_loan_id"), table_name="library_fine")
    op.drop_index(op.f("ix_library_fine_invoice_id"), table_name="library_fine")
    op.drop_index(op.f("ix_library_fine_deleted_at"), table_name="library_fine")
    op.drop_index(op.f("ix_library_fine_created_by_id"), table_name="library_fine")
    op.drop_index(op.f("ix_library_fine_created_at"), table_name="library_fine")
    op.drop_table("library_fine")
    op.drop_index(op.f("ix_course_evaluation_status"), table_name="course_evaluation")
    op.drop_index(op.f("ix_course_evaluation_staff_id"), table_name="course_evaluation")
    op.drop_index(op.f("ix_course_evaluation_semester_id"), table_name="course_evaluation")
    op.drop_index(op.f("ix_course_evaluation_instrument_id"), table_name="course_evaluation")
    op.drop_index(op.f("ix_course_evaluation_deleted_at"), table_name="course_evaluation")
    op.drop_index(op.f("ix_course_evaluation_created_by_id"), table_name="course_evaluation")
    op.drop_index(op.f("ix_course_evaluation_created_at"), table_name="course_evaluation")
    op.drop_index(op.f("ix_course_evaluation_course_offering_id"), table_name="course_evaluation")
    op.drop_table("course_evaluation")
    op.drop_index(op.f("ix_penalty_charge_student_id"), table_name="penalty_charge")
    op.drop_index(op.f("ix_penalty_charge_status"), table_name="penalty_charge")
    op.drop_index(op.f("ix_penalty_charge_invoice_id"), table_name="penalty_charge")
    op.drop_index(op.f("ix_penalty_charge_deleted_at"), table_name="penalty_charge")
    op.drop_index(op.f("ix_penalty_charge_created_by_id"), table_name="penalty_charge")
    op.drop_index(op.f("ix_penalty_charge_created_at"), table_name="penalty_charge")
    op.drop_index(op.f("ix_penalty_charge_charged_on"), table_name="penalty_charge")
    op.drop_table("penalty_charge")
    op.drop_index(op.f("ix_payment_plan_student_id"), table_name="payment_plan")
    op.drop_index(op.f("ix_payment_plan_status"), table_name="payment_plan")
    op.drop_index(op.f("ix_payment_plan_semester_id"), table_name="payment_plan")
    op.drop_index(op.f("ix_payment_plan_invoice_id"), table_name="payment_plan")
    op.drop_index(op.f("ix_payment_plan_deleted_at"), table_name="payment_plan")
    op.drop_index(op.f("ix_payment_plan_created_by_id"), table_name="payment_plan")
    op.drop_index(op.f("ix_payment_plan_created_at"), table_name="payment_plan")
    op.drop_table("payment_plan")
    op.drop_index(op.f("ix_library_reservation_status"), table_name="library_reservation")
    op.drop_index(op.f("ix_library_reservation_record_id"), table_name="library_reservation")
    op.drop_index(op.f("ix_library_reservation_member_id"), table_name="library_reservation")
    op.drop_index(op.f("ix_library_reservation_deleted_at"), table_name="library_reservation")
    op.drop_index(op.f("ix_library_reservation_created_by_id"), table_name="library_reservation")
    op.drop_index(op.f("ix_library_reservation_created_at"), table_name="library_reservation")
    op.drop_index(op.f("ix_library_reservation_collect_by"), table_name="library_reservation")
    op.drop_table("library_reservation")
    op.drop_index("ix_loan_open", table_name="library_loan")
    op.drop_index("ix_loan_member_open", table_name="library_loan")
    op.drop_index(op.f("ix_library_loan_status"), table_name="library_loan")
    op.drop_index(op.f("ix_library_loan_returned_on"), table_name="library_loan")
    op.drop_index(op.f("ix_library_loan_member_id"), table_name="library_loan")
    op.drop_index(op.f("ix_library_loan_library_id"), table_name="library_loan")
    op.drop_index(op.f("ix_library_loan_due_on"), table_name="library_loan")
    op.drop_index(op.f("ix_library_loan_deleted_at"), table_name="library_loan")
    op.drop_index(op.f("ix_library_loan_created_by_id"), table_name="library_loan")
    op.drop_index(op.f("ix_library_loan_created_at"), table_name="library_loan")
    op.drop_index(op.f("ix_library_loan_copy_id"), table_name="library_loan")
    op.drop_table("library_loan")
    op.drop_index(op.f("ix_dunning_notice_student_id"), table_name="dunning_notice")
    op.drop_index(op.f("ix_dunning_notice_sent_on"), table_name="dunning_notice")
    op.drop_index(op.f("ix_dunning_notice_level"), table_name="dunning_notice")
    op.drop_index(op.f("ix_dunning_notice_invoice_id"), table_name="dunning_notice")
    op.drop_index(op.f("ix_dunning_notice_deleted_at"), table_name="dunning_notice")
    op.drop_index(op.f("ix_dunning_notice_created_by_id"), table_name="dunning_notice")
    op.drop_index(op.f("ix_dunning_notice_created_at"), table_name="dunning_notice")
    op.drop_index("ix_dunning_ladder", table_name="dunning_notice")
    op.drop_table("dunning_notice")
    op.drop_index("ix_member_person", table_name="library_member")
    op.drop_index(op.f("ix_library_member_student_id"), table_name="library_member")
    op.drop_index(op.f("ix_library_member_status"), table_name="library_member")
    op.drop_index(op.f("ix_library_member_staff_id"), table_name="library_member")
    op.drop_index(op.f("ix_library_member_membership_number"), table_name="library_member")
    op.drop_index(op.f("ix_library_member_expires_on"), table_name="library_member")
    op.drop_index(op.f("ix_library_member_deleted_at"), table_name="library_member")
    op.drop_index(op.f("ix_library_member_created_by_id"), table_name="library_member")
    op.drop_index(op.f("ix_library_member_created_at"), table_name="library_member")
    op.drop_index(op.f("ix_library_member_borrower_category"), table_name="library_member")
    op.drop_table("library_member")
    op.drop_index(op.f("ix_institution_transfer_student_id"), table_name="institution_transfer")
    op.drop_index(op.f("ix_institution_transfer_status"), table_name="institution_transfer")
    op.drop_index("ix_institution_transfer_queue", table_name="institution_transfer")
    op.drop_index(op.f("ix_institution_transfer_direction"), table_name="institution_transfer")
    op.drop_index(op.f("ix_institution_transfer_deleted_at"), table_name="institution_transfer")
    op.drop_index(op.f("ix_institution_transfer_created_by_id"), table_name="institution_transfer")
    op.drop_index(op.f("ix_institution_transfer_created_at"), table_name="institution_transfer")
    op.drop_index(op.f("ix_institution_transfer_applicant_id"), table_name="institution_transfer")
    op.drop_table("institution_transfer")
    op.drop_index(op.f("ix_quality_indicator_unit_id"), table_name="quality_indicator")
    op.drop_index(op.f("ix_quality_indicator_programme_id"), table_name="quality_indicator")
    op.drop_index(op.f("ix_quality_indicator_performance"), table_name="quality_indicator")
    op.drop_index(op.f("ix_quality_indicator_deleted_at"), table_name="quality_indicator")
    op.drop_index(op.f("ix_quality_indicator_created_by_id"), table_name="quality_indicator")
    op.drop_index(op.f("ix_quality_indicator_created_at"), table_name="quality_indicator")
    op.drop_index(op.f("ix_quality_indicator_code"), table_name="quality_indicator")
    op.drop_index(op.f("ix_quality_indicator_academic_year_id"), table_name="quality_indicator")
    op.drop_index("ix_indicator_scope", table_name="quality_indicator")
    op.drop_table("quality_indicator")
    op.drop_index(op.f("ix_quality_audit_unit_id"), table_name="quality_audit")
    op.drop_index(op.f("ix_quality_audit_status"), table_name="quality_audit")
    op.drop_index(op.f("ix_quality_audit_programme_id"), table_name="quality_audit")
    op.drop_index("ix_quality_audit_open", table_name="quality_audit")
    op.drop_index(op.f("ix_quality_audit_kind"), table_name="quality_audit")
    op.drop_index(op.f("ix_quality_audit_deleted_at"), table_name="quality_audit")
    op.drop_index(op.f("ix_quality_audit_created_by_id"), table_name="quality_audit")
    op.drop_index(op.f("ix_quality_audit_created_at"), table_name="quality_audit")
    op.drop_index(op.f("ix_quality_audit_conducted_on"), table_name="quality_audit")
    op.drop_table("quality_audit")
    op.drop_index(op.f("ix_late_payment_rule_status"), table_name="late_payment_rule")
    op.drop_index(op.f("ix_late_payment_rule_sponsorship"), table_name="late_payment_rule")
    op.drop_index(op.f("ix_late_payment_rule_programme_id"), table_name="late_payment_rule")
    op.drop_index(op.f("ix_late_payment_rule_deleted_at"), table_name="late_payment_rule")
    op.drop_index(op.f("ix_late_payment_rule_created_by_id"), table_name="late_payment_rule")
    op.drop_index(op.f("ix_late_payment_rule_created_at"), table_name="late_payment_rule")
    op.drop_index(op.f("ix_late_payment_rule_academic_year_id"), table_name="late_payment_rule")
    op.drop_table("late_payment_rule")
    op.drop_index(op.f("ix_acquisition_request_status"), table_name="acquisition_request")
    op.drop_index(op.f("ix_acquisition_request_deleted_at"), table_name="acquisition_request")
    op.drop_index(op.f("ix_acquisition_request_created_by_id"), table_name="acquisition_request")
    op.drop_index(op.f("ix_acquisition_request_created_at"), table_name="acquisition_request")
    op.drop_index(op.f("ix_acquisition_request_course_id"), table_name="acquisition_request")
    op.drop_table("acquisition_request")
    op.drop_index(op.f("ix_loan_policy_library_id"), table_name="loan_policy")
    op.drop_index(op.f("ix_loan_policy_deleted_at"), table_name="loan_policy")
    op.drop_index(op.f("ix_loan_policy_created_by_id"), table_name="loan_policy")
    op.drop_index(op.f("ix_loan_policy_created_at"), table_name="loan_policy")
    op.drop_index(op.f("ix_loan_policy_borrower_category"), table_name="loan_policy")
    op.drop_table("loan_policy")
    op.drop_index(op.f("ix_library_stock_take_status"), table_name="library_stock_take")
    op.drop_index(op.f("ix_library_stock_take_library_id"), table_name="library_stock_take")
    op.drop_index(op.f("ix_library_stock_take_deleted_at"), table_name="library_stock_take")
    op.drop_index(op.f("ix_library_stock_take_created_by_id"), table_name="library_stock_take")
    op.drop_index(op.f("ix_library_stock_take_created_at"), table_name="library_stock_take")
    op.drop_table("library_stock_take")
    op.drop_index("ix_copy_shelf", table_name="catalogue_copy")
    op.drop_index(op.f("ix_catalogue_copy_status"), table_name="catalogue_copy")
    op.drop_index(op.f("ix_catalogue_copy_record_id"), table_name="catalogue_copy")
    op.drop_index(op.f("ix_catalogue_copy_library_id"), table_name="catalogue_copy")
    op.drop_index(op.f("ix_catalogue_copy_deleted_at"), table_name="catalogue_copy")
    op.drop_index(op.f("ix_catalogue_copy_created_by_id"), table_name="catalogue_copy")
    op.drop_index(op.f("ix_catalogue_copy_created_at"), table_name="catalogue_copy")
    op.drop_index(op.f("ix_catalogue_copy_call_number"), table_name="catalogue_copy")
    op.drop_index(op.f("ix_catalogue_copy_barcode"), table_name="catalogue_copy")
    op.drop_table("catalogue_copy")
    op.drop_index("ix_calendar_event_window", table_name="calendar_event")
    op.drop_index(op.f("ix_calendar_event_starts_on"), table_name="calendar_event")
    op.drop_index(op.f("ix_calendar_event_semester_id"), table_name="calendar_event")
    op.drop_index(op.f("ix_calendar_event_kind"), table_name="calendar_event")
    op.drop_index(op.f("ix_calendar_event_is_published"), table_name="calendar_event")
    op.drop_index(op.f("ix_calendar_event_deleted_at"), table_name="calendar_event")
    op.drop_index(op.f("ix_calendar_event_created_by_id"), table_name="calendar_event")
    op.drop_index(op.f("ix_calendar_event_created_at"), table_name="calendar_event")
    op.drop_index(op.f("ix_calendar_event_audience"), table_name="calendar_event")
    op.drop_index(op.f("ix_calendar_event_academic_year_id"), table_name="calendar_event")
    op.drop_table("calendar_event")
    op.drop_index(op.f("ix_student_id_card_student_id"), table_name="student_id_card")
    op.drop_index(op.f("ix_student_id_card_status"), table_name="student_id_card")
    op.drop_index(op.f("ix_student_id_card_serial"), table_name="student_id_card")
    op.drop_index(op.f("ix_student_id_card_issued_on"), table_name="student_id_card")
    op.drop_index(op.f("ix_student_id_card_expires_on"), table_name="student_id_card")
    op.drop_index(op.f("ix_student_id_card_deleted_at"), table_name="student_id_card")
    op.drop_index(op.f("ix_student_id_card_created_by_id"), table_name="student_id_card")
    op.drop_index(op.f("ix_student_id_card_created_at"), table_name="student_id_card")
    op.drop_index(op.f("ix_student_id_card_barcode"), table_name="student_id_card")
    op.drop_index("ix_id_card_live", table_name="student_id_card")
    op.drop_table("student_id_card")
    op.drop_index(op.f("ix_library_deleted_at"), table_name="library")
    op.drop_index(op.f("ix_library_created_by_id"), table_name="library")
    op.drop_index(op.f("ix_library_created_at"), table_name="library")
    op.drop_index(op.f("ix_library_campus_id"), table_name="library")
    op.drop_table("library")
    op.drop_index("ix_catalogue_title", table_name="catalogue_record")
    op.drop_index(op.f("ix_catalogue_record_student_id"), table_name="catalogue_record")
    op.drop_index(op.f("ix_catalogue_record_published_year"), table_name="catalogue_record")
    op.drop_index(op.f("ix_catalogue_record_material_kind"), table_name="catalogue_record")
    op.drop_index(op.f("ix_catalogue_record_issn"), table_name="catalogue_record")
    op.drop_index(op.f("ix_catalogue_record_isbn"), table_name="catalogue_record")
    op.drop_index(op.f("ix_catalogue_record_is_searchable"), table_name="catalogue_record")
    op.drop_index(op.f("ix_catalogue_record_deleted_at"), table_name="catalogue_record")
    op.drop_index(op.f("ix_catalogue_record_created_by_id"), table_name="catalogue_record")
    op.drop_index(op.f("ix_catalogue_record_created_at"), table_name="catalogue_record")
    op.drop_index(op.f("ix_catalogue_record_classification"), table_name="catalogue_record")
    op.drop_table("catalogue_record")
    op.drop_index(op.f("ix_evaluation_instrument_is_published"), table_name="evaluation_instrument")
    op.drop_index(op.f("ix_evaluation_instrument_deleted_at"), table_name="evaluation_instrument")
    op.drop_index(
        op.f("ix_evaluation_instrument_created_by_id"), table_name="evaluation_instrument"
    )
    op.drop_index(op.f("ix_evaluation_instrument_created_at"), table_name="evaluation_instrument")
    op.drop_table("evaluation_instrument")
    op.drop_index(
        op.f("ix_e_resource_subscription_is_active"), table_name="e_resource_subscription"
    )
    op.drop_index(
        op.f("ix_e_resource_subscription_expires_on"), table_name="e_resource_subscription"
    )
    op.drop_index(
        op.f("ix_e_resource_subscription_deleted_at"), table_name="e_resource_subscription"
    )
    op.drop_index(
        op.f("ix_e_resource_subscription_created_by_id"), table_name="e_resource_subscription"
    )
    op.drop_index(
        op.f("ix_e_resource_subscription_created_at"), table_name="e_resource_subscription"
    )
    op.drop_table("e_resource_subscription")
