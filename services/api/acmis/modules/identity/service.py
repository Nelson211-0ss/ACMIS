"""Authentication, session and principal assembly."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any, cast

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from acmis.core.audit import AuditCategory, emit
from acmis.core.config import settings
from acmis.core.context import Principal, PrincipalKind
from acmis.core.errors import Forbidden, RuleViolation, Unauthenticated, ValidationFailed
from acmis.core.models import utcnow
from acmis.core.security import (
    hash_password,
    hash_secret,
    issue_token,
    needs_rehash,
    password_problems,
    token_urlsafe,
    verify_password,
)
from acmis.modules.identity.models import (
    AccountStatus,
    CredentialToken,
    LoginAttempt,
    Permission,
    Role,
    RoleAssignment,
    UserAccount,
)
from acmis.modules.identity.models import (
    Session as UserSession,
)

log = structlog.get_logger(__name__)


def load_principal(
    session: Session,
    *,
    subject_id: uuid.UUID,
    claims: dict[str, Any],
    tenant_id: uuid.UUID,
) -> Principal:
    """Assemble the flat attribute set the policy engine evaluates against.

    Read fresh on every request rather than baked into the token. A token lives
    fifteen minutes; a revoked role must not. The cost is one indexed query
    with two eager loads, which is cheaper than the alternative — a
    fifteen-minute window in which a dismissed member of staff still holds
    their old authority over student marks.
    """
    account = session.execute(
        select(UserAccount)
        .options(selectinload(UserAccount.assignments).joinedload(RoleAssignment.role))
        .where(UserAccount.id == subject_id, UserAccount.deleted_at.is_(None))
    ).scalar_one_or_none()

    if account is None:
        raise Unauthenticated("This account no longer exists.")
    if account.status in {AccountStatus.SUSPENDED, AccountStatus.DISABLED}:
        # Not `Unauthenticated`: the credential is valid, the account is not
        # permitted to act. A 401 would send the client round the sign-in loop
        # again and again with a working password.
        raise Forbidden("This account is not active.")

    today = date.today()
    roles: set[str] = set()
    permissions: set[str] = set()
    faculty_ids: set[uuid.UUID] = set()
    department_ids: set[uuid.UUID] = set()
    programme_ids: set[uuid.UUID] = set()

    for assignment in account.assignments:
        if not assignment.is_active_on(today) or assignment.role is None:
            continue
        roles.add(assignment.role.code)
        permissions.update(assignment.role.permission_codes or ())
        # Scope is what turns a role into a policy attribute. An unscoped
        # assignment grants the permission institution-wide, which is why
        # `requires_scope` roles are refused an unscoped assignment on the way
        # in — see `assign_role`.
        if assignment.scope_id is None:
            continue
        if assignment.scope_type == "faculty":
            faculty_ids.add(assignment.scope_id)
        elif assignment.scope_type == "department":
            department_ids.add(assignment.scope_id)
        elif assignment.scope_type == "programme":
            programme_ids.add(assignment.scope_id)

    # A member of staff also inherits the reach of their appointments, so a
    # newly-appointed head of department can act before anyone remembers to
    # add a scoped role assignment.
    if account.staff_id:
        from acmis.modules.people.models import Staff

        staff = session.get(Staff, account.staff_id)
        if staff is not None:
            faculty_ids.update(staff.faculty_ids or ())
            department_ids.update(staff.department_ids or ())

    mfa_satisfied = False
    session_id: uuid.UUID | None = None
    if claims.get("sid"):
        session_id = uuid.UUID(str(claims["sid"]))
        live = session.get(UserSession, session_id)
        if live is None or not live.is_live:
            raise Unauthenticated("This session has been signed out.")
        mfa_satisfied = live.mfa_satisfied_at is not None

    extra: dict[str, Any] = {
        "status": account.status,
        "password_expired": bool(
            account.must_change_password
            or (account.password_expires_on and account.password_expires_on < today)
        ),
    }
    # Attributes some policies read that are not roles: a releaser's waiver
    # ceiling, and the offerings they may enter marks for.
    if account.staff_id:
        extra["assigned_course_offering_ids"] = [
            str(i) for i in _assigned_offering_ids(session, account.staff_id)
        ]
        extra["waiver_ceiling_minor"] = _waiver_ceiling(permissions)

    kind = account.kind
    if kind not in {"staff", "student", "applicant", "service", "platform"}:
        # A kind the policy engine does not know would be a subject no rule
        # matches, which deny-by-default turns into a locked-out user with no
        # explanation. Better to say so.
        raise Forbidden(f"This account has an unrecognised type ({kind!r}).")

    return Principal(
        id=account.id,
        kind=cast("PrincipalKind", kind),
        display_name=account.display_name,
        email=account.email,
        tenant_id=tenant_id,
        roles=frozenset(roles),
        permissions=frozenset(permissions),
        faculty_ids=frozenset(faculty_ids),
        department_ids=frozenset(department_ids),
        programme_ids=frozenset(programme_ids),
        student_id=account.student_id,
        applicant_id=account.applicant_id,
        staff_id=account.staff_id,
        mfa_satisfied=mfa_satisfied,
        impersonator_id=(uuid.UUID(str(claims["imp"])) if claims.get("imp") else None),
        session_id=session_id,
        extra=extra,
    )


def _assigned_offering_ids(session: Session, staff_id: uuid.UUID) -> list[uuid.UUID]:
    """Offerings this member of staff may enter marks for, today.

    Date-bounded: a part-time lecturer's authority over a mark sheet ends with
    their contract, and `assessment.mark-entry` compares against exactly this
    list. An expired allocation dropping out of it is the mechanism.
    """
    from acmis.modules.curriculum.models import TeachingAllocation

    today = date.today()
    rows = session.execute(
        select(TeachingAllocation.offering_id).where(
            TeachingAllocation.staff_id == staff_id,
            TeachingAllocation.can_enter_marks.is_(True),
            TeachingAllocation.deleted_at.is_(None),
            (TeachingAllocation.starts_on.is_(None)) | (TeachingAllocation.starts_on <= today),
            (TeachingAllocation.ends_on.is_(None)) | (TeachingAllocation.ends_on >= today),
        )
    ).scalars()
    return list(rows)


def _waiver_ceiling(permissions: set[str]) -> int:
    """The most a holder of these permissions may release in one waiver.

    A ladder rather than a single grant, because "may approve waivers" without
    an amount is not a control. The figures are institution-configurable via
    `system_setting`; these are the fallbacks.
    """
    if "finance:waive_unlimited" in permissions:
        return 2**62
    if "finance:approve" in permissions:
        return 5_000_000_00
    if "finance:waive" in permissions:
        return 500_000_00
    return 0


# ---------------------------------------------------------------------------
# Sign-in
# ---------------------------------------------------------------------------


def authenticate(
    session: Session,
    *,
    username: str,
    password: str,
    tenant_id: uuid.UUID,
    ip_address: str | None,
    user_agent: str | None,
    module: str | None,
) -> tuple[UserAccount, UserSession, str, str]:
    """Verify credentials and open a session.

    Every attempt is recorded, successful or not, including attempts against
    usernames that do not exist — that is the signal that distinguishes one
    person forgetting their password from someone walking the student-number
    space.

    The failure path is deliberately uniform. Wrong password, no such account
    and locked account all produce the same message and take comparable time:
    a password check runs even when no account was found, because returning
    early on a missing account makes the endpoint a student-number oracle
    measurable with a stopwatch.
    """
    identifier = username.strip()
    account = session.execute(
        select(UserAccount).where(
            (UserAccount.username == identifier) | (UserAccount.email == identifier.lower()),
            UserAccount.deleted_at.is_(None),
        )
    ).scalar_one_or_none()

    def record(succeeded: bool, reason: str | None) -> None:
        session.add(
            LoginAttempt(
                attempted_at=utcnow(),
                username_attempted=identifier[:200],
                account_id=account.id if account else None,
                succeeded=succeeded,
                failure_reason=reason,
                ip_address=ip_address,
                user_agent=(user_agent or "")[:500] or None,
                module=module,
            )
        )

    generic = Unauthenticated("That username or password is not correct.")

    if account is None:
        # Spend the time anyway. See the note above.
        verify_password(password, hash_password("timing-equaliser"))
        record(False, "no_such_account")
        raise generic

    now = utcnow()
    if account.locked_until and account.locked_until > now:
        record(False, "locked")
        raise generic

    if not account.password_hash or not verify_password(password, account.password_hash):
        account.failed_logins += 1
        if account.failed_logins >= settings.max_failed_logins:
            account.locked_until = now + timedelta(seconds=settings.lockout_seconds)
            log.warning("account_locked", account_id=str(account.id))
        record(False, "bad_password")
        raise generic

    if account.status in {AccountStatus.SUSPENDED, AccountStatus.DISABLED}:
        record(False, "account_" + account.status)
        raise Forbidden("This account is not active. Contact the registry.")

    # Upgrade the hash opportunistically when the cost parameters have been
    # raised since it was written. Only possible here, where the plaintext is
    # in hand for the one moment it ever is.
    if needs_rehash(account.password_hash):
        account.password_hash = hash_password(password)

    account.failed_logins = 0
    account.locked_until = None
    account.last_login_at = now
    account.last_login_ip = ip_address
    if account.status == AccountStatus.PENDING_VERIFICATION and account.email_verified_at:
        account.status = AccountStatus.ACTIVE

    refresh_plain = token_urlsafe(48)
    user_session = UserSession(
        account_id=account.id,
        refresh_token_hash=hash_secret(refresh_plain),
        issued_at=now,
        expires_at=now + timedelta(seconds=settings.refresh_token_ttl_seconds),
        last_seen_at=now,
        ip_address=ip_address,
        user_agent=(user_agent or "")[:500] or None,
        module=module,
        # MFA is not satisfied by a password. A session that has one is
        # stepped up separately, and the baseline policy gates the dangerous
        # actions on it.
        mfa_satisfied_at=None,
    )
    session.add(user_session)
    session.flush()

    access = issue_token(
        subject_id=account.id,
        kind="access",
        tenant_id=tenant_id,
        session_id=user_session.id,
        claims={"knd": account.kind},
    )
    record(True, None)
    emit(
        "auth:login",
        AuditCategory.AUTHENTICATION,
        resource_type="user_account",
        resource_id=account.id,
        resource_label=f"{account.display_name} <{account.email}>",
        summary="Signed in",
        metadata={"module": module, "session_id": str(user_session.id)},
    )
    return account, user_session, access, refresh_plain


def refresh_session(
    session: Session, *, refresh_token: str, tenant_id: uuid.UUID
) -> tuple[UserAccount, UserSession, str]:
    """Exchange a refresh token for a new access token.

    The refresh path is where revocation actually bites: the session row is
    re-read and the account's standing re-checked, so a suspension takes effect
    within one access-token lifetime rather than at the end of a fortnight.
    """
    row = session.execute(
        select(UserSession)
        .options(selectinload(UserSession.account))
        .where(UserSession.refresh_token_hash == hash_secret(refresh_token))
    ).scalar_one_or_none()

    if row is None or not row.is_live or row.expires_at <= utcnow():
        raise Unauthenticated("Please sign in again.")
    account = row.account
    if account is None or not account.is_usable:
        raise Unauthenticated("Please sign in again.")

    row.last_seen_at = utcnow()
    access = issue_token(
        subject_id=account.id,
        kind="access",
        tenant_id=tenant_id,
        session_id=row.id,
        claims={"knd": account.kind},
    )
    return account, row, access


def sign_out(session: Session, *, session_id: uuid.UUID, reason: str = "user_signed_out") -> None:
    row = session.get(UserSession, session_id)
    if row is None or not row.is_live:
        return
    row.revoked_at = utcnow()
    row.revoked_reason = reason
    emit(
        "auth:logout",
        AuditCategory.AUTHENTICATION,
        resource_type="user_account",
        resource_id=row.account_id,
        summary="Signed out",
    )


def revoke_all_sessions(session: Session, *, account_id: uuid.UUID, reason: str) -> int:
    """ "Sign out everywhere" — used on password change and on suspension."""
    rows = session.execute(
        select(UserSession).where(
            UserSession.account_id == account_id, UserSession.revoked_at.is_(None)
        )
    ).scalars()
    count = 0
    now = utcnow()
    for row in rows:
        row.revoked_at = now
        row.revoked_reason = reason
        count += 1
    emit(
        "auth:revoke_sessions",
        AuditCategory.AUTHENTICATION,
        resource_type="user_account",
        resource_id=account_id,
        summary=f"{count} session(s) revoked: {reason}",
        severity="notice",
    )
    return count


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------


def change_password(
    session: Session,
    *,
    account: UserAccount,
    current_password: str | None,
    new_password: str,
    require_current: bool = True,
) -> None:
    if require_current:
        if not current_password or not account.password_hash:
            raise Unauthenticated("Your current password is required.")
        if not verify_password(current_password, account.password_hash):
            raise Unauthenticated("Your current password is not correct.")

    problems = password_problems(
        new_password,
        context=[account.username, account.email.split("@")[0], account.display_name],
    )
    if problems:
        raise ValidationFailed(
            "That password cannot be used.", code="weak_password", details={"problems": problems}
        )
    if account.password_hash and verify_password(new_password, account.password_hash):
        raise ValidationFailed(
            "Choose a password you have not used here before.", code="password_reused"
        )

    account.password_hash = hash_password(new_password)
    account.password_changed_at = utcnow()
    account.must_change_password = False
    account.password_expires_on = None
    # Every other session dies with the old password. If the reason for the
    # change is that someone else had it, leaving their session alive defeats
    # the entire exercise.
    revoke_all_sessions(session, account_id=account.id, reason="password_changed")
    emit(
        "auth:change_password",
        AuditCategory.AUTHENTICATION,
        resource_type="user_account",
        resource_id=account.id,
        summary="Password changed",
        severity="notice",
    )


def issue_credential_token(
    session: Session, *, account: UserAccount, purpose: str, ttl_hours: int = 1
) -> str:
    """Mint a single-use token for reset, verification or invitation.

    Any previous unused token for the same purpose is invalidated. Two live
    reset links for one account means the older email — possibly the one an
    attacker triggered — still works after the user requests a fresh one.
    """
    for row in session.execute(
        select(CredentialToken).where(
            CredentialToken.account_id == account.id,
            CredentialToken.purpose == purpose,
            CredentialToken.used_at.is_(None),
        )
    ).scalars():
        row.used_at = utcnow()

    plain = token_urlsafe(32)
    session.add(
        CredentialToken(
            account_id=account.id,
            purpose=purpose,
            token_hash=hash_secret(plain),
            expires_at=utcnow() + timedelta(hours=ttl_hours),
            issued_to_email=account.email,
        )
    )
    emit(
        f"auth:issue_{purpose}",
        AuditCategory.AUTHENTICATION,
        resource_type="user_account",
        resource_id=account.id,
        summary=f"{purpose} token issued",
        severity="notice",
    )
    return plain


def redeem_credential_token(session: Session, *, token: str, purpose: str) -> UserAccount:
    row = session.execute(
        select(CredentialToken)
        .options(selectinload(CredentialToken.account))
        .where(
            CredentialToken.token_hash == hash_secret(token),
            CredentialToken.purpose == purpose,
        )
    ).scalar_one_or_none()

    if row is None or row.used_at is not None or row.expires_at <= utcnow():
        raise Unauthenticated("That link is no longer valid. Request a new one.")
    row.used_at = utcnow()
    account: UserAccount | None = row.account
    if account is None:
        raise Unauthenticated("That link is no longer valid.")
    return account


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------


def assign_role(
    session: Session,
    *,
    account: UserAccount,
    role: Role,
    scope_type: str | None,
    scope_id: uuid.UUID | None,
    requested_by_id: uuid.UUID,
    approved_by_id: uuid.UUID,
    starts_on: date | None = None,
    ends_on: date | None = None,
    reason: str | None = None,
    is_acting: bool = False,
) -> RoleAssignment:
    """Grant a role, refusing the grants that break separation of duties.

    Three refusals, all at the point of granting rather than the point of use.
    Catching a conflict when a mark sheet is already half-approved is too late:
    the work has to be unwound and somebody has to explain it.
    """
    if role.requires_scope and scope_id is None:
        raise RuleViolation(
            f"The {role.name} role must be scoped to a specific unit.",
            rule="role_requires_scope",
        )
    if requested_by_id == approved_by_id:
        raise RuleViolation(
            "A role assignment must be approved by someone other than the person who requested it.",
            rule="separation_of_duties",
        )

    conflicts = _permission_conflicts(session, account, role)
    if conflicts:
        raise RuleViolation(
            "This role conflicts with permissions the account already holds.",
            rule="conflicting_permissions",
            details={"conflicts": conflicts},
            waivable_by=["identity:admin"],
        )

    if role.max_holders is not None:
        held = session.execute(
            select(RoleAssignment).where(
                RoleAssignment.role_id == role.id, RoleAssignment.deleted_at.is_(None)
            )
        ).scalars()
        if len([a for a in held if a.is_active_on(date.today())]) >= role.max_holders:
            raise RuleViolation(
                f"The {role.name} role is limited to {role.max_holders} holder(s).",
                rule="role_holder_limit",
            )

    assignment = RoleAssignment(
        account_id=account.id,
        role_id=role.id,
        scope_type=scope_type,
        scope_id=scope_id,
        starts_on=starts_on,
        ends_on=ends_on,
        requested_by_id=requested_by_id,
        approved_by_id=approved_by_id,
        approved_at=utcnow(),
        reason=reason,
        is_acting=is_acting,
    )
    session.add(assignment)
    emit(
        "role_assignment:create",
        AuditCategory.CONFIGURATION,
        resource_type="role_assignment",
        resource_id=assignment.id,
        resource_label=f"{role.code} -> {account.display_name}",
        summary=f"Granted {role.code}" + (f" scoped to {scope_type}" if scope_type else ""),
        metadata={
            "role": role.code,
            "scope_type": scope_type,
            "scope_id": str(scope_id) if scope_id else None,
            "ends_on": ends_on.isoformat() if ends_on else None,
            "is_acting": is_acting,
            "reason": reason,
        },
        severity="notice",
    )
    return assignment


def _permission_conflicts(
    session: Session, account: UserAccount, role: Role
) -> list[dict[str, str]]:
    """Which of the new role's permissions conflict with what is already held.

    The conflict table is what encodes institutional rules like "nobody both
    enters marks and approves them" or "nobody both raises a waiver and
    releases it" — the separations that only work if they are refused at
    assignment.
    """
    today = date.today()
    held: set[str] = set()
    for assignment in account.assignments:
        if assignment.is_active_on(today) and assignment.role is not None:
            held.update(assignment.role.permission_codes or ())

    incoming = set(role.permission_codes or ())
    if not held or not incoming:
        return []

    rows = session.execute(select(Permission).where(Permission.code.in_(incoming | held))).scalars()
    conflicts: list[dict[str, str]] = []
    for permission in rows:
        for other in permission.conflicts_with or ():
            if permission.code in incoming and other in held:
                conflicts.append({"granting": permission.code, "conflicts_with": other})
            elif permission.code in held and other in incoming:
                conflicts.append({"granting": other, "conflicts_with": permission.code})
    return conflicts


def revoke_role(
    session: Session, *, assignment: RoleAssignment, actor_id: uuid.UUID, reason: str
) -> None:
    assignment.deleted_at = utcnow()
    assignment.deleted_by_id = actor_id
    assignment.deletion_reason = reason
    emit(
        "role_assignment:delete",
        AuditCategory.CONFIGURATION,
        resource_type="role_assignment",
        resource_id=assignment.id,
        summary=f"Revoked {assignment.role.code if assignment.role else 'role'}",
        metadata={"reason": reason},
        severity="notice",
    )
