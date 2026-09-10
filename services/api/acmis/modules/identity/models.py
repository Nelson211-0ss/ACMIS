"""Accounts, sessions, roles and permissions.

Roles here are a *convenience layer over ABAC*, not the authorization model.
A role is a named bundle of permission codes; the policy bundle is what decides
anything. That split is deliberate: "registrar" is a useful thing for a human
administrator to assign, and a useless thing to write a rule against, because
the rule you actually need is "the registrar of *this* faculty, for a student
in *that* programme, during the registration window". Roles answer "what is
this person", policies answer "may they do this to that, now".
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

from acmis.core.models import TenantBase, TenantRecord


class AccountKind(StrEnum):
    STAFF = "staff"
    STUDENT = "student"
    APPLICANT = "applicant"
    #: An external examiner, a sponsor's officer, an alumnus requesting a
    #: transcript. Modelled as its own kind because they get accounts but no
    #: staff or student record, and every policy that says
    #: `subject.kind == "staff"` must not accidentally cover them.
    EXTERNAL = "external"
    SERVICE = "service"


class AccountStatus(StrEnum):
    INVITED = "invited"
    PENDING_VERIFICATION = "pending_verification"
    ACTIVE = "active"
    #: Wrong password too many times. Clears itself after `lockout_seconds`.
    LOCKED = "locked"
    #: An administrator turned it off. Does not clear itself.
    SUSPENDED = "suspended"
    #: Graduated, left, contract ended. Kept so the audit trail still resolves
    #: the name of whoever entered a mark in 2027.
    DISABLED = "disabled"


class UserAccount(TenantRecord):
    """A way to sign in. One person may hold exactly one.

    Identity is unified on purpose. A tutor who is also studying for a masters
    at the same university is one account with a staff record and a student
    record, not two logins — the alternative is a person who can see their own
    marks through one session and edit them through another, which is the exact
    hole `assessment.separation-of-duties` exists to close.
    """

    __tablename__ = "user_account"

    #: Institutional identifier: staff number, student number, or the email an
    #: applicant registered with. Case-insensitively unique.
    username: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(200), nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    phone: Mapped[str | None] = mapped_column(String(40))
    phone_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    kind: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=AccountStatus.INVITED, index=True
    )
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)

    password_hash: Mapped[str | None] = mapped_column(String(200))
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Forces a change at next sign-in. Set on every administratively-reset
    #: password, so a counter reset cannot become a shared credential.
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    password_expires_on: Mapped[date | None] = mapped_column(Date)

    mfa_secret: Mapped[str | None] = mapped_column(String(120))
    mfa_enrolled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Hashed one-time recovery codes. Hashed, because a support agent who can
    #: read them can sign in as anyone who has enrolled.
    mfa_recovery_hashes: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)), nullable=False, default=list
    )

    #: Set for staff whose institution federates to its own identity provider.
    #: A federated account holds no password hash at all.
    external_idp: Mapped[str | None] = mapped_column(String(60))
    external_subject: Mapped[str | None] = mapped_column(String(200))

    failed_logins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_ip: Mapped[str | None] = mapped_column(String(60))

    #: Links to the domain records this account speaks for. Nullable, and more
    #: than one may be set at once — see the note on unified identity.
    staff_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    student_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    applicant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)

    preferences: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    assignments: Mapped[list[RoleAssignment]] = relationship(
        back_populates="account", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        # Case-insensitive uniqueness. `LOWER(username)` in the index rather
        # than lowercasing on write, so `Jane.Doe` and `jane.doe` collide
        # without rewriting what the user typed.
        Index(
            "uq_user_account_username",
            "username",
            unique=True,
            postgresql_ops={"username": "text_pattern_ops"},
        ),
        Index("uq_user_account_email_lower", "email", unique=True),
        Index("ix_user_account_kind_status", "kind", "status"),
    )

    @property
    def is_usable(self) -> bool:
        return self.status == AccountStatus.ACTIVE and self.deleted_at is None


class Permission(TenantBase):
    """A capability code, e.g. `results:approve`.

    A table rather than a Python enum so an institution can see the full list
    in the admin UI, and so a new module's permissions arrive by migration
    instead of a redeploy. `is_high_risk` drives the extra confirmation in the
    UI and the MFA gate in the baseline policy.
    """

    __tablename__ = "permission"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(60), unique=True, nullable=False, index=True)
    module: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_high_risk: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: Codes that must not be held by the same person. Enforced when a role is
    #: assigned, so separation of duties is refused at the point of granting
    #: rather than discovered at the point of use.
    conflicts_with: Mapped[list[str]] = mapped_column(
        ARRAY(String(60)), nullable=False, default=list
    )


class Role(TenantRecord):
    """A named bundle of permissions, e.g. "Faculty Registrar"."""

    __tablename__ = "role"

    code: Mapped[str] = mapped_column(String(60), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    permission_codes: Mapped[list[str]] = mapped_column(
        ARRAY(String(60)), nullable=False, default=list
    )
    #: Shipped roles cannot be deleted or have their code changed — a policy
    #: that names `registrar` must keep resolving. Their permission sets can
    #: still be edited by the institution.
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: Requires a scope when assigned: a "Head of Department" assignment is
    #: meaningless without saying which department.
    requires_scope: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    max_holders: Mapped[int | None] = mapped_column(Integer)


class RoleAssignment(TenantRecord):
    """One person holding one role, optionally scoped and time-bounded.

    Scope is what turns a role into an ABAC attribute: assigning "Head of
    Department" scoped to Computer Science is what puts that department's id
    into `subject.department_ids`, which is what every unit-scoped rule
    compares against.

    Time bounds matter more than they look. An acting dean covers a sabbatical
    for one semester, and the authority has to *expire* — the alternative is
    the standing observation that most over-privileged accounts in any
    university are people who once acted in a role and nobody revoked it.
    """

    __tablename__ = "role_assignment"

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("role.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    scope_type: Mapped[str | None] = mapped_column(String(30))
    scope_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    starts_on: Mapped[date | None] = mapped_column(Date)
    ends_on: Mapped[date | None] = mapped_column(Date, index=True)
    #: Who asked for this and who signed it off — different people, enforced by
    #: `identity.separation-of-duties`.
    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(String(500))
    is_acting: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    account: Mapped[UserAccount] = relationship(back_populates="assignments")
    role: Mapped[Role] = relationship(lazy="joined")

    __table_args__ = (
        UniqueConstraint(
            "account_id", "role_id", "scope_type", "scope_id", name="uq_role_assignment"
        ),
        Index("ix_role_assignment_active", "account_id", "ends_on"),
    )

    def is_active_on(self, when: date) -> bool:
        if self.deleted_at is not None:
            return False
        if self.starts_on and when < self.starts_on:
            return False
        return not (self.ends_on and when > self.ends_on)


class Session(TenantRecord):
    """A signed-in session, server-side.

    Server-side despite the JWT, because a stateless token cannot be revoked
    and "sign out everywhere" and "lock this account now" are both requirements
    here. The access token is short-lived and checked cryptographically; the
    refresh path checks this row, so a suspended account loses access within
    one access-token lifetime rather than at the end of a fortnight.
    """

    __tablename__ = "user_session"

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: Hash of the refresh token, never the token. A stolen database dump must
    #: not be a set of working sessions.
    refresh_token_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(String(120))
    mfa_satisfied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ip_address: Mapped[str | None] = mapped_column(String(60))
    user_agent: Mapped[str | None] = mapped_column(String(500))
    #: Which module app the session was opened from. Shown in "your active
    #: sessions" so a user recognises their own.
    module: Mapped[str | None] = mapped_column(String(40))
    #: Set when a platform support session is acting through this one.
    impersonator_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    account: Mapped[UserAccount] = relationship()

    @property
    def is_live(self) -> bool:
        return self.revoked_at is None


class CredentialToken(TenantRecord):
    """Single-use tokens: password reset, email verification, invitation.

    Stored hashed and marked used on redemption. Single-use is enforced here
    rather than by expiry alone, because a reset link sits in an inbox and a
    shared institutional mailbox is a normal thing at a university registry.
    """

    __tablename__ = "credential_token"

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), nullable=False, index=True
    )
    purpose: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    issued_to_email: Mapped[str | None] = mapped_column(String(200))
    issued_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    #: Eager-loaded on redemption: the token is looked up by hash and the
    #: account is needed in the same breath, so a lazy load here would be a
    #: guaranteed second query on the one path that must be fast and simple.
    account: Mapped[UserAccount] = relationship()


class LoginAttempt(TenantBase):
    """Every attempt, successful or not.

    Its own table rather than a counter on the account, because the useful
    questions are temporal: is one account being guessed at, or is one address
    walking the whole student-number space? The second is invisible in a
    per-account counter, and it is the one that matters.
    """

    __tablename__ = "login_attempt"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    #: What was typed, kept even when no such account exists — that is the
    #: enumeration signal.
    username_attempted: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    succeeded: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True)
    failure_reason: Mapped[str | None] = mapped_column(String(60))
    ip_address: Mapped[str | None] = mapped_column(String(60), index=True)
    user_agent: Mapped[str | None] = mapped_column(String(500))
    module: Mapped[str | None] = mapped_column(String(40))

    __table_args__ = (
        Index("ix_login_attempt_ip_time", "ip_address", "attempted_at"),
        Index("ix_login_attempt_user_time", "username_attempted", "attempted_at"),
    )
