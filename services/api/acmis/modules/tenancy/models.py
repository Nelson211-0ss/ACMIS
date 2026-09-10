"""Control-plane tables: the universities themselves.

This is the only module whose tables live in the shared `acmis_control`
database. Everything here is about the platform's relationship with an
institution — never about students.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
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

from acmis.core.models import ControlBase, ControlRecord


class TenantStatus(StrEnum):
    PROVISIONING = "provisioning"
    ACTIVE = "active"
    #: Past due, or in an off-season the institution has asked to pause. Reads
    #: work, writes do not — chosen over a hard block because locking a
    #: registry out mid-semester over an invoice punishes students for a
    #: dispute between two finance departments.
    READ_ONLY = "read_only"
    SUSPENDED = "suspended"
    #: Data retained, access closed, awaiting the contractual purge date.
    ARCHIVED = "archived"
    FAILED = "failed"


class Tenant(ControlRecord):
    """One university.

    `database_name` rather than a full DSN, normally: the DSN is built from the
    template in settings so a credential rotation is one environment variable
    and not 200 UPDATEs. `database_dsn` overrides it for the tenant that has
    outgrown the shared cluster and been moved to its own — which is the
    migration path database-per-tenant exists to make possible.
    """

    __tablename__ = "tenant"

    slug: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    short_name: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=TenantStatus.PROVISIONING, index=True
    )

    database_name: Mapped[str] = mapped_column(String(63), unique=True, nullable=False)
    database_dsn: Mapped[str | None] = mapped_column(Text)
    region: Mapped[str] = mapped_column(String(20), nullable=False, default="eu-west-1")

    # --- institutional identity ------------------------------------------
    country_code: Mapped[str] = mapped_column(String(2), nullable=False, default="UG")
    city: Mapped[str | None] = mapped_column(String(120))
    locale: Mapped[str] = mapped_column(String(10), nullable=False, default="en-UG")
    timezone: Mapped[str] = mapped_column(String(40), nullable=False, default="Africa/Kampala")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="UGX")
    #: The regulator this institution reports to — drives which statutory
    #: return templates the governance module offers.
    regulator_code: Mapped[str | None] = mapped_column(String(20))
    #: Charter/accreditation number, printed on transcripts and certificates.
    accreditation_number: Mapped[str | None] = mapped_column(String(60))
    website: Mapped[str | None] = mapped_column(String(200))
    support_email: Mapped[str | None] = mapped_column(String(200))

    # --- branding ---------------------------------------------------------
    #: Served to every module app so one deployment renders as the right
    #: university. Colours are validated as OKLCH or hex on the way in.
    logo_url: Mapped[str | None] = mapped_column(String(500))
    crest_url: Mapped[str | None] = mapped_column(String(500))
    brand_primary: Mapped[str | None] = mapped_column(String(40))
    brand_accent: Mapped[str | None] = mapped_column(String(40))

    enabled_features: Mapped[list[str]] = mapped_column(
        ARRAY(String(60)), nullable=False, default=list
    )
    runtime_settings: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    #: Bumped whenever this tenant's ABAC overlay changes. The API caches a
    #: compiled bundle per revision, so a policy edit takes effect on the next
    #: request everywhere without a restart or a cache-invalidation message.
    policy_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Alembic revision the tenant database is on. Fanning migrations across
    #: hundreds of databases is only safe if you can see which ones lag.
    schema_revision: Mapped[str | None] = mapped_column(String(40))
    schema_migrated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    onboarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    suspension_reason: Mapped[str | None] = mapped_column(String(500))
    #: Contractual date after which an archived tenant's database is destroyed.
    purge_after: Mapped[date | None] = mapped_column(Date)

    domains: Mapped[list[TenantDomain]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan", lazy="selectin"
    )
    subscription: Mapped[Subscription | None] = relationship(
        back_populates="tenant", uselist=False, cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_tenant_status_region", "status", "region"),
        Index("ix_tenant_purge", "purge_after", postgresql_where=purge_after.isnot(None)),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Tenant {self.slug} {self.status}>"


class TenantDomain(ControlRecord):
    """Host names that resolve to this tenant.

    Universities want `acmis.mak.ac.ug`, not `mak.acmis.example`. A tenant can
    hold several — its platform subdomain, its vanity domain, and per-module
    hosts during a phased rollout — and exactly one is `is_primary`, which is
    what links and emails are built from.
    """

    __tablename__ = "tenant_domain"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False, index=True
    )
    hostname: Mapped[str] = mapped_column(String(253), unique=True, nullable=False, index=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verification_token: Mapped[str | None] = mapped_column(String(80))

    tenant: Mapped[Tenant] = relationship(back_populates="domains")

    __table_args__ = (
        # One primary per tenant, enforced by a partial unique index rather
        # than application code, which is the only version that survives two
        # concurrent "make this primary" requests.
        Index(
            "uq_tenant_domain_primary",
            "tenant_id",
            unique=True,
            postgresql_where=is_primary.is_(True),
        ),
    )


class Plan(ControlRecord):
    """A commercial plan. Which modules are on, and the hard ceilings."""

    __tablename__ = "plan"

    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    #: Module codes this plan turns on: {"admissions", "assessment", ...}
    included_modules: Mapped[list[str]] = mapped_column(
        ARRAY(String(40)), nullable=False, default=list
    )
    #: Priced per enrolled student per year — the only metric a university
    #: finance committee will accept, since it scales with their own income.
    price_per_student_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    max_students: Mapped[int | None] = mapped_column(Integer)
    max_staff: Mapped[int | None] = mapped_column(Integer)
    max_api_requests_per_day: Mapped[int | None] = mapped_column(Integer)
    support_tier: Mapped[str] = mapped_column(String(20), nullable=False, default="standard")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Subscription(ControlRecord):
    __tablename__ = "subscription"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("plan.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="trialing")
    started_on: Mapped[date] = mapped_column(Date, nullable=False)
    renews_on: Mapped[date | None] = mapped_column(Date)
    trial_ends_on: Mapped[date | None] = mapped_column(Date)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Days of write access after the renewal date lapses, before READ_ONLY.
    grace_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    billed_student_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(Text)

    tenant: Mapped[Tenant] = relationship(back_populates="subscription")
    plan: Mapped[Plan] = relationship(lazy="joined")


class PlatformUser(ControlRecord):
    """Staff of the platform operator, not of any university."""

    __tablename__ = "platform_user"

    email: Mapped[str] = mapped_column(String(200), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    #: {"platform:admin"} or {"platform:support"}. Two grants, on purpose:
    #: support can look, admin can change, and nobody has both by default.
    permissions: Mapped[list[str]] = mapped_column(ARRAY(String(60)), nullable=False, default=list)
    mfa_secret: Mapped[str | None] = mapped_column(String(120))
    mfa_enrolled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_logins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ImpersonationSession(ControlRecord):
    """A support session inside a tenant.

    Every one of these is a person from outside the university looking at its
    records, so each is short-lived, needs a stated reason and a ticket
    reference, and is visible to the tenant's own governance module. The
    baseline policy makes them read-only; this table is how the university can
    see that we were there at all.
    """

    __tablename__ = "impersonation_session"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False, index=True
    )
    platform_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("platform_user.id"), nullable=False, index=True
    )
    #: The tenant account being acted as, when the session assumes one.
    target_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    ticket_reference: Mapped[str | None] = mapped_column(String(80))
    #: Set when the university's own administrator approved the session. Some
    #: contracts require it; where they do, `approved_by_id` being null means
    #: the session cannot start.
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actions_taken: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class PlatformAuditEvent(ControlBase):
    """The platform's own append-only trail. Never contains student data."""

    __tablename__ = "platform_audit_event"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    request_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    actor_label: Mapped[str | None] = mapped_column(String(200))
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False, default="success")
    resource_type: Mapped[str | None] = mapped_column(String(60))
    resource_id: Mapped[str | None] = mapped_column(String(80))
    summary: Mapped[str | None] = mapped_column(Text)
    changes: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    event_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    ip_address: Mapped[str | None] = mapped_column(String(60))

    __table_args__ = (Index("ix_platform_audit_tenant_time", "tenant_id", "occurred_at"),)


class TenantMigration(ControlRecord):
    """One migration run against one tenant database.

    A fan-out across 200 databases will partially fail — a lock timeout, a
    tenant mid-restore. Recording each attempt is what makes the retry safe
    and makes "which universities are on the old schema right now" answerable
    without connecting to all of them.
    """

    __tablename__ = "tenant_migration"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_revision: Mapped[str | None] = mapped_column(String(40))
    to_revision: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    triggered_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    __table_args__ = (
        UniqueConstraint("tenant_id", "to_revision", "started_at", name="uq_tenant_migration_run"),
    )
