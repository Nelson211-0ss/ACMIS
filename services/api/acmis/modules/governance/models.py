"""Governance, reporting and audit.

The `audit_event` table is the reason this module exists, and it is the one
table in ACMIS that the application is not permitted to change. `UPDATE` and
`DELETE` are revoked from the application role in the tenant migration; a trail
the application can rewrite proves nothing in the dispute it exists to settle.

It carries no `deleted_at` and no `version` for the same reason: it does not
inherit `TenantRecord`, because every mixin on that class describes a mutable
row.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from acmis.core.models import TenantBase, TenantRecord, utcnow


class AuditEvent(TenantBase):
    """One recorded action. Append-only, ten-year retention.

    Wide and denormalised on purpose. An audit row must remain readable when
    the account that made the change has been deleted, the course renumbered
    and the faculty dissolved — so the actor's name, their roles at the time,
    and the resource's label are copied in rather than joined. A trail that
    depends on joins to be legible degrades exactly as fast as the records
    around it.
    """

    __tablename__ = "audit_event"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, index=True
    )
    #: Ties every row written during one HTTP request together.
    request_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    #: Ties rows across requests that form one logical operation — a bulk mark
    #: upload, a semester roll-over, a fee-run.
    correlation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)

    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    actor_kind: Mapped[str] = mapped_column(String(20), nullable=False, default="staff")
    actor_label: Mapped[str | None] = mapped_column(String(200))
    #: Roles held at the moment of the action. A person's roles change; what
    #: matters in a review is what they held when they acted.
    actor_roles: Mapped[list[str]] = mapped_column(ARRAY(String(60)), nullable=False, default=list)
    #: Set when platform support was acting through this account.
    impersonator_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)

    module: Mapped[str | None] = mapped_column(String(40), index=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False, default="success", index=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="info", index=True)

    resource_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    resource_id: Mapped[str | None] = mapped_column(String(80), index=True)
    resource_label: Mapped[str | None] = mapped_column(String(300))
    #: Who the record is *about*, when that differs from the resource. Lets a
    #: student see the trail of actions taken on them across every table, which
    #: `governance.audit-access/own-trail` grants them.
    subject_student_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    subject_staff_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)

    summary: Mapped[str | None] = mapped_column(Text)
    #: [{field, old, new}] — redacted for secrets and special-category data
    #: before it ever reaches this column.
    changes: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    event_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    #: The authorization decision behind the action. Without these, "who
    #: allowed this" is a question the system cannot answer — and it is the
    #: first question asked after anything goes wrong.
    decision_policy_id: Mapped[str | None] = mapped_column(String(80), index=True)
    decision_rule_id: Mapped[str | None] = mapped_column(String(80))
    policy_bundle_version: Mapped[str | None] = mapped_column(String(20))

    ip_address: Mapped[str | None] = mapped_column(String(60), index=True)
    user_agent: Mapped[str | None] = mapped_column(String(500))
    http_method: Mapped[str | None] = mapped_column(String(10))
    http_path: Mapped[str | None] = mapped_column(String(300))

    __table_args__ = (
        # The four queries an audit review actually runs. Composite, because a
        # single-column index on a table with tens of millions of rows still
        # reads most of them for "this student, last term".
        Index("ix_audit_resource", "resource_type", "resource_id", "occurred_at"),
        Index("ix_audit_actor_time", "actor_id", "occurred_at"),
        Index("ix_audit_subject_student", "subject_student_id", "occurred_at"),
        Index("ix_audit_denials", "outcome", "occurred_at", postgresql_where=outcome == "denied"),
        Index("ix_audit_category_time", "category", "occurred_at"),
    )


class AccessLog(TenantBase):
    """Reads of sensitive records. Also append-only.

    Separate from `audit_event` because the volumes differ by orders of
    magnitude and the retention differs too: a read log is high-volume, useful
    for a year, and answers a data-protection question rather than an academic
    one. Mixing them makes the write trail unreadable.
    """

    __tablename__ = "access_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, index=True
    )
    request_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    actor_label: Mapped[str | None] = mapped_column(String(200))
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    resource_id: Mapped[str | None] = mapped_column(String(80), index=True)
    subject_student_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    subject_staff_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    #: Which fields were actually returned, and which were masked. The
    #: difference is the point: "opened the record" and "read the disability
    #: disclosure" are different accesses.
    fields_returned: Mapped[list[str]] = mapped_column(
        ARRAY(String(60)), nullable=False, default=list
    )
    fields_masked: Mapped[list[str]] = mapped_column(
        ARRAY(String(60)), nullable=False, default=list
    )
    #: Row count, for a list or an export. One read of 40,000 records is not
    #: the same event as one read of one.
    record_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    purpose: Mapped[str | None] = mapped_column(String(300))
    ip_address: Mapped[str | None] = mapped_column(String(60))
    module: Mapped[str | None] = mapped_column(String(40))

    __table_args__ = (
        Index("ix_access_log_actor_time", "actor_id", "occurred_at"),
        Index("ix_access_log_subject", "subject_student_id", "occurred_at"),
    )


class PolicyOverlay(TenantRecord):
    """A tenant's own ABAC policy.

    Loaded on top of the shipped bundle. `document` is the same YAML-derived
    shape the builtin files use, validated on save so a broken policy is
    rejected at authoring time rather than discovered as an outage.

    Bumping the tenant's `policy_revision` is what makes a saved change take
    effect: the API caches a compiled bundle per revision, so the next request
    anywhere in the fleet picks it up without a restart.
    """

    __tablename__ = "abac_policy"

    policy_id: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    document: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    #: Overlay policies live at 50+; below that is reserved for the builtin
    #: prohibitions, which a tenant may not undercut.
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    #: Author and approver — a policy change is itself separation-of-duties.
    authored_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    change_reason: Mapped[str | None] = mapped_column(Text)
    #: Result of the last simulation run against real historical requests.
    #: Enabling a policy without one is possible but flagged, because the
    #: common way to lock a university out of its own system is a deny rule
    #: that matches more than its author expected.
    last_simulation: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class PolicyChangeLog(TenantBase):
    """Every version a policy has ever had. Append-only.

    A policy's own history, kept separately from `audit_event` so that
    "reconstruct the rules as at 3 March" is a single query rather than a
    replay of diffs.
    """

    __tablename__ = "abac_policy_change"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    policy_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, index=True
    )
    changed_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    change_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    document_before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    document_after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    reason: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (UniqueConstraint("policy_id", "revision", name="uq_policy_change_revision"),)


class ReportKind(StrEnum):
    OPERATIONAL = "operational"
    #: A return to the regulator or ministry. Its shape is fixed by them.
    STATUTORY = "statutory"
    MANAGEMENT = "management"
    ACCREDITATION = "accreditation"


class ReportDefinition(TenantRecord):
    """A saved, parameterised report.

    `query_spec` is a structured description — dataset, filters, groupings —
    and never SQL. A report definition is authored by staff through the UI and
    stored in the tenant database; accepting SQL there would make every
    report author a database administrator with the credentials of the
    process.
    """

    __tablename__ = "report_definition"

    code: Mapped[str] = mapped_column(String(60), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    module: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    query_spec: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    parameters: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    #: Permission required to run it. A report is a read of many records at
    #: once and inherits the sensitivity of the most sensitive one.
    required_permission: Mapped[str | None] = mapped_column(String(60))
    contains_personal_data: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: Cron expression for a scheduled return.
    schedule: Mapped[str | None] = mapped_column(String(60))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ReportRun(TenantRecord):
    """One execution of a report, with its parameters and its row count.

    Row count is recorded because it is the number that matters in an access
    review, and because a report that returned 40,000 personal records is an
    export whether or not it was called one.
    """

    __tablename__ = "report_run"

    definition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("report_definition.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: Whether the run touches personal data is a property of the definition,
    #: and it decides whether this is an export.
    definition: Mapped[ReportDefinition] = relationship(viewonly=True, lazy="joined")
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued", index=True)
    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    #: Mandatory for anything touching personal data —
    #: `governance.data-export` attaches a `require:reason` obligation.
    purpose: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    row_count: Mapped[int | None] = mapped_column(Integer)
    output_format: Mapped[str] = mapped_column(String(10), nullable=False, default="xlsx")
    attachment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    #: Recipient stamped into the file, so a leaked copy is traceable.
    watermark: Mapped[str | None] = mapped_column(String(200))
    error: Mapped[str | None] = mapped_column(Text)
    #: Exports expire. A file that lives forever in object storage is a copy of
    #: the database with none of its access controls.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class StatutoryReturn(TenantRecord):
    """A submission to a regulator, and its acknowledgement.

    Kept because the institution has to prove it filed on time and prove what
    it filed. `payload_snapshot` is the exact data submitted: the underlying
    records keep changing, and a return re-derived next year will not match the
    one the regulator holds.
    """

    __tablename__ = "statutory_return"

    code: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    regulator: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    academic_year_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("academic_year.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    period_label: Mapped[str] = mapped_column(String(40), nullable=False)
    due_on: Mapped[date | None] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", index=True)
    payload_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    #: Validation findings, so a return is not submitted with known errors.
    validation_findings: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    prepared_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    acknowledgement_reference: Mapped[str | None] = mapped_column(String(120))
    attachment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    __table_args__ = (
        UniqueConstraint(
            "code", "academic_year_id", "period_label", name="uq_statutory_return_period"
        ),
    )


class DataRequest(TenantRecord):
    """A subject access, correction or erasure request.

    Data-protection law in most of the jurisdictions ACMIS serves gives a
    student the right to see what is held about them and to have errors
    corrected, on a statutory clock. Erasure is almost always refused for an
    academic record — the institution has a legal obligation to retain it —
    and the refusal must be reasoned, which is why `outcome` is text and not a
    boolean.
    """

    __tablename__ = "data_request"

    reference: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    #: `access`, `correction`, `erasure`, `portability`, `objection`.
    kind: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    subject_student_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    subject_staff_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    subject_name: Mapped[str] = mapped_column(String(300), nullable=False)
    requested_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    #: Statutory deadline, computed from `requested_on`. The whole reason this
    #: table exists is that the clock is external and enforceable.
    due_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    identity_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="received", index=True)
    handled_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    outcome: Mapped[str | None] = mapped_column(Text)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attachment_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )


class RetentionRule(TenantRecord):
    """How long each kind of record is kept, and what happens then.

    Academic records are kept effectively forever; application documents from
    unsuccessful candidates are not, and keeping them is a liability rather
    than an asset. Encoding the schedule makes the purge job auditable and
    makes the institution's own policy inspectable.
    """

    __tablename__ = "retention_rule"

    resource_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    retain_years: Mapped[int | None] = mapped_column(Integer)
    #: `permanent`, `anonymise`, `delete`, `archive`. Anonymisation is the
    #: usual answer: the statistics are needed for reporting, the identity is
    #: not.
    action: Mapped[str] = mapped_column(String(20), nullable=False, default="archive")
    legal_basis: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_run_affected: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (UniqueConstraint("resource_type", name="uq_retention_resource"),)
