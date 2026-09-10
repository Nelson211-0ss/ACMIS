"""Standards interoperability: LTI 1.3 Advantage, OneRoster 1.2, QTI 3.0.

ACMIS is the **platform** in LTI terms, not the tool. It issues launches into
external tools — a publisher's courseware, an H5P activity, a plagiarism
service, a proctoring provider — and receives grades back from them. That
direction matters: every LTI library on PyPI implements the *tool* side, so
this is written against the specification rather than wrapped around one.

Why standards at all, rather than a bespoke integration per vendor: a
university that adopts ACMIS already owns content, and content vendors already
speak LTI and QTI. Supporting them is the difference between "migrate
everything" and "plug in what you have". `docs/standards.md` records what each
module was modelled on and why.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from acmis.core.models import TenantBase, TenantRecord, utcnow


class LtiTool(TenantRecord):
    """An external tool this institution has registered.

    The platform half of an LTI 1.3 registration: we hold the tool's client
    id, its OIDC login endpoint, its JWKS URL (so its signed responses can be
    verified) and the services it is allowed to use.

    `deployment_id` is per registration rather than global, per the
    specification: the same tool registered for the Faculty of Medicine and
    for Engineering is two deployments, and a grade posted against one cannot
    land in the other.
    """

    __tablename__ = "lti_tool"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    #: The tool's OAuth client id, as issued by us.
    client_id: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    #: The tool's issuer, for verifying the JWTs it sends back.
    issuer: Mapped[str] = mapped_column(String(300), nullable=False)
    #: Where to send the OIDC authentication request.
    oidc_login_url: Mapped[str] = mapped_column(String(500), nullable=False)
    #: Where a successful launch lands.
    target_link_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    #: The tool's public keys. Fetched and cached rather than stored inline, so
    #: a tool rotating its keys does not require a support ticket.
    jwks_url: Mapped[str | None] = mapped_column(String(500))
    public_key_pem: Mapped[str | None] = mapped_column(Text)
    deployment_id: Mapped[str] = mapped_column(String(80), nullable=False)

    #: Which LTI Advantage services this tool may use. Granted individually:
    #: a content tool needs Deep Linking and nothing else, and giving it grade
    #: write access because it was convenient is how a courseware vendor ends
    #: up able to change marks.
    allow_deep_linking: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    allow_grade_services: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    allow_names_and_roles: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: Names and Role Provisioning discloses a class list — names and email
    #: addresses — to a third party. Off by default, and when on, this decides
    #: whether the tool sees addresses at all.
    disclose_emails: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: Custom parameters merged into every launch, e.g. a vendor's course key.
    custom_parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    #: Scope this registration to part of the institution. Null means
    #: institution-wide, which is a deliberate decision rather than a default.
    unit_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_launch_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    launch_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (UniqueConstraint("client_id", "deployment_id", name="uq_lti_deployment"),)


class LtiResourceLink(TenantRecord):
    """A specific piece of tool content placed in a course space.

    Created by Deep Linking: the lecturer launches the tool, picks a chapter or
    an activity, and the tool returns a content item that becomes one of these.
    Modelled separately from `Material` because a resource link carries a
    launch identity the tool recognises across sessions — that is what lets a
    student resume where they left off in the vendor's own system.
    """

    __tablename__ = "lti_resource_link"

    tool_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("lti_tool.id", ondelete="CASCADE"), nullable=False, index=True
    )
    space_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("course_space.id", ondelete="CASCADE"), index=True
    )
    course_offering_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("course_offering.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    #: The tool's own URL for this item, from the Deep Linking response.
    url: Mapped[str | None] = mapped_column(String(1000))
    custom: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    #: `window`, `iframe`, `embed` — the tool's presentation preference.
    presentation: Mapped[str] = mapped_column(String(20), nullable=False, default="iframe")
    #: When the tool reports a grade, which component of the course's
    #: assessment scheme it lands in. Same narrow seam as the online
    #: assessments: a component score on a draft mark sheet, never a final
    #: mark, never past the approval chain.
    assessment_component_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("assessment_component.id", ondelete="SET NULL")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    tool: Mapped[LtiTool] = relationship()
    line_items: Mapped[list[LtiLineItem]] = relationship(
        back_populates="resource_link", cascade="all, delete-orphan"
    )


class LtiLineItem(TenantRecord):
    """A gradable column, in Assignment and Grade Services terms.

    One per gradable activity in a tool. The tool posts scores against it; we
    hold the maximum and the mapping to our own assessment component. Named
    "line item" because that is what the specification calls it, and matching
    the vocabulary is what makes an integration debuggable against the spec
    rather than against our documentation.
    """

    __tablename__ = "lti_line_item"

    resource_link_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("lti_resource_link.id", ondelete="CASCADE"), index=True
    )
    tool_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("lti_tool.id", ondelete="CASCADE"), nullable=False, index=True
    )
    course_offering_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("course_offering.id", ondelete="CASCADE"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String(300), nullable=False)
    score_maximum: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False, default=100)
    #: The tool's own identifier for the activity, echoed back on every score.
    resource_id: Mapped[str | None] = mapped_column(String(200), index=True)
    #: An external identifier the tool and the institution agreed on, per the
    #: OneRoster/LTI integration points.
    tag: Mapped[str | None] = mapped_column(String(120))
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    assessment_component_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("assessment_component.id", ondelete="SET NULL")
    )
    #: Scores arrive continuously as students work. Pushing each one into the
    #: mark sheet would mean thousands of writes to the academic record; they
    #: accumulate here and are pushed deliberately, like an online assessment.
    pushed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    resource_link: Mapped[LtiResourceLink | None] = relationship(back_populates="line_items")

    __table_args__ = (CheckConstraint("score_maximum > 0", name="line_item_maximum_positive"),)


class LtiScore(TenantBase):
    """A score posted by a tool. Append-only.

    Every posting is kept, not just the latest. A tool that reports 40 and
    then 85 for the same student has either seen more work or has a bug, and
    which of those it is can only be established from the sequence. `timestamp`
    is the tool's own, and a score older than one already recorded is rejected
    per the specification — out-of-order delivery is normal on a flaky link.
    """

    __tablename__ = "lti_score"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    line_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("lti_line_item.id", ondelete="CASCADE"), nullable=False, index=True
    )
    student_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    #: The tool's timestamp, from the score payload.
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, index=True
    )
    score_given: Mapped[float | None] = mapped_column(Numeric(8, 2))
    score_maximum: Mapped[float | None] = mapped_column(Numeric(8, 2))
    #: `Initialized`, `Started`, `InProgress`, `Submitted`, `Completed` — the
    #: specification's activity progress vocabulary.
    activity_progress: Mapped[str] = mapped_column(String(20), nullable=False)
    #: `NotReady`, `Failed`, `Pending`, `PendingManual`, `FullyGraded`. Only a
    #: `FullyGraded` score is eligible to reach the mark sheet.
    grading_progress: Mapped[str] = mapped_column(String(20), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    #: The raw payload, for when an integration disagrees about what it sent.
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (Index("ix_lti_score_current", "line_item_id", "student_id", "timestamp"),)


class LtiNonce(TenantBase):
    """Used OIDC nonces, so a captured launch cannot be replayed.

    Required by the security framework and easy to skip, which is why it is a
    table rather than a comment: without it an intercepted `id_token` can be
    presented again, and an LTI launch is an authenticated session.
    """

    __tablename__ = "lti_nonce"

    nonce: Mapped[str] = mapped_column(String(120), primary_key=True)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, index=True
    )
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    client_id: Mapped[str | None] = mapped_column(String(120))


class PlatformKey(TenantRecord):
    """The signing keys for this institution's LTI platform.

    Per tenant, not per deployment: a tool trusts one JWKS per platform, and
    every university on ACMIS is a distinct platform with its own issuer. One
    shared key across tenants would let a tool registered by one university
    verify a launch minted for another.

    Rotation is why there is more than one: a new key is published to the JWKS
    before it signs anything, so tools that cache the key set have fetched it
    by the time it is used.
    """

    __tablename__ = "lti_platform_key"

    kid: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    algorithm: Mapped[str] = mapped_column(String(10), nullable=False, default="RS256")
    public_key_pem: Mapped[str] = mapped_column(Text, nullable=False)
    #: Encrypted at rest by the deployment's secret manager in production; the
    #: column holds the ciphertext, never the raw PEM.
    private_key_ref: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    #: Published but not yet signing, during a rotation.
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExternalIdentifier(TenantRecord):
    """Mapping between our UUIDs and an external system's identifiers.

    OneRoster calls its identifier a `sourcedId`, and a consuming system keys
    everything on it forever. Exposing our internal UUID as the sourcedId would
    work — until a data migration changes one, at which point every downstream
    system has orphans.

    So the mapping is explicit and stable, and it works both ways: it is also
    how a legacy student number from the system ACMIS replaced stays
    resolvable, which is what makes a migration survivable.
    """

    __tablename__ = "external_identifier"

    #: `oneroster`, `edfi`, `legacy_sis`, `library`, `payroll`, or a vendor.
    system: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    #: Our side.
    resource_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    resource_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    #: Their side.
    external_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    external_type: Mapped[str | None] = mapped_column(String(60))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint(
            "system", "resource_type", "resource_id", name="uq_external_identifier_ours"
        ),
        UniqueConstraint("system", "external_id", name="uq_external_identifier_theirs"),
    )


class ContentPackage(TenantRecord):
    """An imported SCORM, cmi5 or QTI package.

    Institutions arrive with content: a QTI question bank exported from
    Moodle, a SCORM course from a publisher. Recording the import — what came
    in, what it produced, what failed — is what makes a migration auditable,
    and a migration nobody can audit is one nobody trusts.
    """

    __tablename__ = "content_package"

    #: `qti_2p1`, `qti_3p0`, `scorm_1p2`, `scorm_2004`, `cmi5`, `common_cartridge`.
    format: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    source_system: Mapped[str | None] = mapped_column(String(80))
    attachment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    space_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("course_space.id", ondelete="SET NULL"), index=True
    )
    question_bank_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("question_bank.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="uploaded", index=True)
    items_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    items_imported: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Per-item failures with the reason. An import that silently drops the
    #: eleven questions it could not parse is worse than one that refuses.
    failures: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    imported_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class XapiStatement(TenantBase):
    """An xAPI statement from a tool or content package. Append-only.

    Stored in the tenant's own database rather than shipped to an external
    Learning Record Store by default, because these statements are behavioural
    data about identified students and the institution should decide where that
    goes. Forwarding to an LRS is configuration, not the default.
    """

    __tablename__ = "xapi_statement"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    stored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, index=True
    )
    #: The statement's own timestamp, which may precede storage.
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actor_student_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    #: The verb IRI, e.g. `http://adlnet.gov/expapi/verbs/completed`.
    verb: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    object_iri: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    course_offering_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    tool_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    result_score_scaled: Mapped[float | None] = mapped_column(Numeric(5, 4))
    result_success: Mapped[bool | None] = mapped_column(Boolean)
    result_completion: Mapped[bool | None] = mapped_column(Boolean)
    statement: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (Index("ix_xapi_student_time", "actor_student_id", "occurred_at"),)
