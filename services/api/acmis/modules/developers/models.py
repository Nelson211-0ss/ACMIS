"""The developer portal: API clients, keys, webhooks, sandbox.

Universities integrate. A library system needs to know who is registered, the
national student loans board needs enrolment confirmation, a mobile-money
provider posts payment callbacks, and the institution's own mobile app is just
another API client. So the platform's integration surface is a first-class
module rather than an afterthought bolted onto an internal API.

The security position is stated once and enforced by
`developers.machine-tokens`: **a token can never do anything the account it
was issued for could not do by hand.** A client's effective authority is the
intersection of its scopes and its owner's permissions. Without that, the
developer portal is a privilege-escalation route — mint a token with generous
scopes, and the ABAC layer that governs the rest of the system is bypassed.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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


class ClientEnvironment(StrEnum):
    #: Points at a seeded copy of the tenant's own shape with synthetic people
    #: in it. Real integrations are built against real-looking data or they
    #: break on their first day in production.
    SANDBOX = "sandbox"
    LIVE = "live"


class ApiClient(TenantRecord):
    """A registered integration."""

    __tablename__ = "api_client"

    client_id: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    #: The account answerable for it. Its permissions are the ceiling on
    #: everything this client can do.
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    owner_email: Mapped[str] = mapped_column(String(200), nullable=False)
    #: A team address, so a client does not become unmaintainable when its
    #: author leaves — which they will, and the integration will not.
    support_email: Mapped[str | None] = mapped_column(String(200))
    environment: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ClientEnvironment.SANDBOX, index=True
    )
    #: `machine`, `web`, `mobile`, `service_account`. Decides which OAuth
    #: flows are permitted: only `machine` may use client credentials.
    client_kind: Mapped[str] = mapped_column(String(20), nullable=False, default="machine")
    redirect_uris: Mapped[list[str]] = mapped_column(
        ARRAY(String(500)), nullable=False, default=list
    )
    #: Requested and granted are separate. A developer asks for what they
    #: want; an integration administrator grants a subset, and the grant is
    #: what the token carries.
    requested_scopes: Mapped[list[str]] = mapped_column(
        ARRAY(String(60)), nullable=False, default=list
    )
    granted_scopes: Mapped[list[str]] = mapped_column(
        ARRAY(String(60)), nullable=False, default=list
    )
    #: Addresses calls may originate from. Optional, and the single most
    #: effective control available for a server-to-server integration.
    allowed_ip_ranges: Mapped[list[str]] = mapped_column(
        ARRAY(String(60)), nullable=False, default=list
    )
    rate_limit_per_minute: Mapped[int] = mapped_column(Integer, nullable=False, default=120)
    daily_quota: Mapped[int | None] = mapped_column(Integer)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    suspension_reason: Mapped[str | None] = mapped_column(String(500))
    #: Set by the nightly sweep. An integration nobody has called in six
    #: months is a live credential with no owner watching it.
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    #: Institutions require periodic recertification of integrations.
    review_due_on: Mapped[date | None] = mapped_column(Date, index=True)

    keys: Mapped[list[ApiKey]] = relationship(
        back_populates="client", cascade="all, delete-orphan", lazy="selectin"
    )
    webhooks: Mapped[list[Webhook]] = relationship(
        back_populates="client", cascade="all, delete-orphan"
    )


class ApiKey(TenantRecord):
    """A credential for a client. Stored hashed; shown once.

    The full key is returned exactly once, at creation. After that it can be
    rotated or revoked but never retrieved — `developers.credentials/
    never-reveal` refuses the read outright. `prefix` is kept in clear so the
    console can identify a key, and so a key found leaked in a public
    repository can be revoked without waiting for its owner to notice.
    """

    __tablename__ = "api_key"

    client_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("api_client.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    prefix: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    environment: Mapped[str] = mapped_column(String(20), nullable=False, default="sandbox")
    #: A key's scopes may narrow its client's, never widen them.
    scopes: Mapped[list[str]] = mapped_column(ARRAY(String(60)), nullable=False, default=list)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    #: Every key expires. A credential with no expiry is one nobody will ever
    #: get round to rotating.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_ip: Mapped[str | None] = mapped_column(String(60))
    use_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    revocation_reason: Mapped[str | None] = mapped_column(String(300))
    #: During a rotation both keys work briefly, so an integration can be
    #: redeployed without downtime. The old one carries the overlap window.
    rotated_from_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    rotation_grace_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    client: Mapped[ApiClient] = relationship(back_populates="keys")

    @property
    def is_live(self) -> bool:
        if self.revoked_at is not None:
            return False
        return self.expires_at is None or self.expires_at > utcnow()


class Webhook(TenantRecord):
    """An outbound subscription to platform events."""

    __tablename__ = "webhook"

    client_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("api_client.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    #: e.g. {"student.enrolled", "result.published", "payment.settled"}.
    event_types: Mapped[list[str]] = mapped_column(ARRAY(String(60)), nullable=False, default=list)
    #: HMAC secret for the `t=…,v1=…` signature. Hashed for storage; the plain
    #: value is shown once, like a key.
    secret_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    #: Consecutive failures. At the threshold the webhook is disabled and its
    #: owner told, rather than retried forever — a dead endpoint retried
    #: indefinitely is a self-inflicted outbound flood.
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disabled_reason: Mapped[str | None] = mapped_column(String(300))
    last_delivery_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status_code: Mapped[int | None] = mapped_column(Integer)
    #: Events are queued while an endpoint is down and replayed on request, so
    #: a receiver's outage does not silently lose a semester's enrolments.
    retention_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=72)

    client: Mapped[ApiClient] = relationship(back_populates="webhooks")


class WebhookDelivery(TenantBase):
    """One attempt to deliver one event. Append-only.

    Kept so a receiver can prove it was never called and the platform can
    prove it was. That argument happens on every integration eventually, and
    the response body is the only thing that settles it.
    """

    __tablename__ = "webhook_delivery"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    webhook_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("webhook.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, index=True
    )
    #: The exact bytes signed and sent. Redacted of personal data beyond what
    #: the subscription's scopes allow, before it is stored.
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    response_status: Mapped[int | None] = mapped_column(Integer, index=True)
    response_body: Mapped[str | None] = mapped_column(String(2000))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(String(500))
    succeeded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    __table_args__ = (Index("ix_webhook_delivery_hook_time", "webhook_id", "attempted_at"),)


class PlatformEvent(TenantBase):
    """The outbox. Every event that has happened, whether or not anyone listens.

    A transactional outbox rather than a direct HTTP call from the code that
    made the change. Posting inline means a slow receiver holds a database
    transaction open while a student waits, and a failed post either rolls back
    a legitimate enrolment or is silently dropped. Writing the event in the
    same transaction and delivering it afterwards is the only arrangement where
    the change and the notification cannot disagree.
    """

    __tablename__ = "platform_event"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, index=True
    )
    resource_type: Mapped[str] = mapped_column(String(60), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(80), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    #: Ties the event to the request that caused it, so a webhook receiver's
    #: support question can be traced back into the audit trail.
    request_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    #: Set once the dispatcher has fanned it out to subscriptions.
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    subscriber_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index(
            "ix_platform_event_pending",
            "dispatched_at",
            "occurred_at",
            postgresql_where=dispatched_at.is_(None),
        ),
    )


class IntegrationLog(TenantBase):
    """Inbound API calls from clients. Append-only, short retention.

    Distinct from the audit trail: this is the developer's own log, for
    debugging their integration. It records the request line, the status and
    the timing — never the request body, which would put student data in a log
    the developer's whole team can read.
    """

    __tablename__ = "integration_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    api_key_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    request_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, index=True
    )
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    path: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    #: Set when the call was refused by ABAC, with the deciding policy. The
    #: single most useful line a developer can be shown when their integration
    #: gets a 403 — "your token's scopes do not cover this" instead of a bare
    #: status code.
    denied_reason: Mapped[str | None] = mapped_column(String(200))
    ip_address: Mapped[str | None] = mapped_column(String(60))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    response_bytes: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (Index("ix_integration_log_client_time", "client_id", "occurred_at"),)


class SandboxDataset(TenantRecord):
    """A seeded sandbox for a client to build against.

    Synthetic people, real shapes: a sandbox with three students and no
    retakes produces an integration that falls over in week one of a real
    semester. `seed` is recorded so the same dataset can be regenerated
    identically when a developer needs to reproduce a bug.
    """

    __tablename__ = "sandbox_dataset"

    client_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("api_client.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    #: {"students": 500, "programmes": 12, "semesters": 4, ...}
    shape: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="building")
    built_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Sandboxes expire, or a deployment accumulates hundreds of them.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    reset_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class OAuthGrant(TenantRecord):
    """An authorisation a person gave to a client to act for them.

    For the flows where a client acts on a *user's* behalf — the institution's
    mobile app reading a student's own results. The grant is what makes that
    lawful, it names the scopes the person actually consented to, and the
    person can revoke it. A client acting for a user with no grant is acting
    without consent, however valid its own credentials.
    """

    __tablename__ = "oauth_grant"

    client_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("api_client.id", ondelete="CASCADE"), nullable=False, index=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(String(60)), nullable=False, default=list)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by: Mapped[str | None] = mapped_column(String(20))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("client_id", "account_id", name="uq_oauth_grant"),
        CheckConstraint("expires_at IS NULL OR expires_at > granted_at", name="grant_ordered"),
    )
