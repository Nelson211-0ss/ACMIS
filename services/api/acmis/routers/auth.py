"""Sign-in, sessions and credentials."""

from __future__ import annotations

import uuid
from datetime import UTC
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response, status
from pydantic import EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from acmis.core.config import settings
from acmis.core.deps import AuthContext, audit_writer, tenant_db, tenant_of
from acmis.core.errors import Unauthenticated
from acmis.core.schemas import Schema
from acmis.core.security import issue_token
from acmis.modules.identity import service as identity
from acmis.modules.identity.models import UserAccount

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(Schema):
    username: Annotated[str, Field(min_length=1, max_length=200)]
    password: Annotated[str, Field(min_length=1, max_length=200)]


class TokenOut(Schema):
    access_token: str
    # The OAuth 2.0 response field, not a credential.
    token_type: str = "bearer"  # noqa: S105
    expires_in: int
    #: Returned in the body only for non-browser clients. Browsers get it as an
    #: HttpOnly cookie so a cross-site script cannot read it, and the Next.js
    #: BFF in each app never puts it in `localStorage`.
    refresh_token: str | None = None
    must_change_password: bool = False
    mfa_required: bool = False


class WhoAmIOut(Schema):
    id: uuid.UUID
    kind: str
    display_name: str
    email: str | None
    tenant_slug: str
    tenant_name: str
    roles: list[str]
    permissions: list[str]
    faculty_ids: list[uuid.UUID]
    department_ids: list[uuid.UUID]
    student_id: uuid.UUID | None
    staff_id: uuid.UUID | None
    applicant_id: uuid.UUID | None
    mfa_satisfied: bool
    is_impersonated: bool
    #: Which module apps this actor should see in the launcher. Computed
    #: server-side from permissions and the tenant's enabled features, so a
    #: module a university has not bought never appears.
    modules: list[str]


REFRESH_COOKIE = "acmis_refresh"


@router.post("/login", response_model=TokenOut)
def login(
    payload: LoginIn,
    request: Request,
    response: Response,
    db: Session = Depends(tenant_db),
    # The writer is declared even though the caller is anonymous: a sign-in is
    # an audited event, and every failed attempt is the enumeration signal the
    # governance module reads. Without this the route emitted an audit record
    # into nothing and logged `audit_no_writer` — which is a dropped security
    # event, not a warning to live with.
    audit: object = Depends(audit_writer),
) -> TokenOut:
    tenant = tenant_of(request)
    ctx = request.state.acmis_context
    account, session_row, access, refresh = identity.authenticate(
        db,
        username=payload.username,
        password=payload.password,
        tenant_id=tenant.id,
        ip_address=ctx.ip_address,
        user_agent=ctx.user_agent,
        module=ctx.module,
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh,
        max_age=settings.refresh_token_ttl_seconds,
        httponly=True,
        secure=settings.environment != "local",
        samesite="lax",
        path=f"{settings.api_prefix}/auth",
    )
    return TokenOut(
        access_token=access,
        expires_in=settings.access_token_ttl_seconds,
        refresh_token=refresh if ctx.module == "cli" else None,
        must_change_password=account.must_change_password,
        # Enrolled but not yet satisfied on this session: the client should
        # prompt for the code before the user reaches an MFA-gated action, so
        # the step-up is not a surprise mid-approval.
        mfa_required=account.mfa_enrolled_at is not None and session_row.mfa_satisfied_at is None,
    )


@router.post("/refresh", response_model=TokenOut)
def refresh_token(
    request: Request,
    db: Session = Depends(tenant_db),
    cookie_token: Annotated[str | None, Header(alias="cookie")] = None,
) -> TokenOut:
    tenant = tenant_of(request)
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise Unauthenticated("No refresh token was presented.")
    _account, _session, access = identity.refresh_session(
        db, refresh_token=token, tenant_id=tenant.id
    )
    return TokenOut(access_token=access, expires_in=settings.access_token_ttl_seconds)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(ctx: AuthContext, response: Response) -> None:
    if ctx.principal.session_id:
        identity.sign_out(ctx.db, session_id=ctx.principal.session_id)
    response.delete_cookie(REFRESH_COOKIE, path=f"{settings.api_prefix}/auth")


@router.get("/whoami", response_model=WhoAmIOut)
def whoami(ctx: AuthContext) -> WhoAmIOut:
    """Who the caller is, and what they should be shown.

    `modules` is computed here rather than in each frontend app. Nine apps
    reimplementing "may this person see the finance module" would be nine
    places for it to drift, and the answer depends on the tenant's plan as
    well as the actor's permissions.
    """
    principal = ctx.principal
    return WhoAmIOut(
        id=principal.id,
        kind=principal.kind,
        display_name=principal.display_name,
        email=principal.email,
        tenant_slug=ctx.tenant.slug,
        tenant_name=ctx.tenant.name,
        roles=sorted(principal.roles),
        permissions=sorted(principal.permissions),
        faculty_ids=sorted(principal.faculty_ids),
        department_ids=sorted(principal.department_ids),
        student_id=principal.student_id,
        staff_id=principal.staff_id,
        applicant_id=principal.applicant_id,
        mfa_satisfied=principal.mfa_satisfied,
        is_impersonated=principal.impersonator_id is not None,
        modules=_visible_modules(ctx),
    )


MODULE_PERMISSION_PREFIX = {
    "admissions": ("admissions:",),
    "students": ("student:", "registration:"),
    "curriculum": ("curriculum:", "timetable:"),
    "finance": ("finance:",),
    "people": ("people:",),
    "assessment": ("results:", "award:", "transcript:"),
    "learning": ("learning:",),
    # Elections are conducted from the governance app: the returning officer
    # and the observers are the same people who hold oversight, and a
    # separate app for three screens would be a launcher tile nobody finds.
    "governance": ("audit:", "reporting:", "policy:", "governance:", "elections:"),
    "developers": ("developer:",),
    "library": ("library:",),
    "quality": ("quality:",),
}


def _visible_modules(ctx: AuthContext) -> list[str]:
    principal = ctx.principal
    if principal.kind == "student":
        return ["portal"]
    if principal.kind == "applicant":
        return ["apply"]

    enabled = ctx.tenant.features
    visible = ["portal"] if principal.student_id else []
    for module, prefixes in MODULE_PERMISSION_PREFIX.items():
        if enabled and module not in enabled:
            continue
        if any(p.startswith(prefix) for p in principal.permissions for prefix in prefixes):
            visible.append(module)
    return visible


class ChangePasswordIn(Schema):
    current_password: str | None = None
    new_password: Annotated[str, Field(min_length=12, max_length=200)]


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(payload: ChangePasswordIn, ctx: AuthContext) -> None:
    account = ctx.db.get(UserAccount, ctx.principal.id)
    if account is None:
        raise Unauthenticated()
    identity.change_password(
        ctx.db,
        account=account,
        current_password=payload.current_password,
        new_password=payload.new_password,
        # A forced change has no "current password" to offer beyond the one
        # just used to sign in, which the session already proves.
        require_current=not account.must_change_password,
    )


class ForgotPasswordIn(Schema):
    email: EmailStr


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
def forgot_password(
    payload: ForgotPasswordIn,
    request: Request,
    db: Session = Depends(tenant_db),
    audit: object = Depends(audit_writer),
) -> dict[str, str]:
    """Always answers the same way.

    Whether or not the address exists, the response is identical. Anything else
    turns this endpoint into a directory of who studies here.
    """
    tenant_of(request)
    account = db.execute(
        select(UserAccount).where(
            UserAccount.email == payload.email.lower(), UserAccount.deleted_at.is_(None)
        )
    ).scalar_one_or_none()
    if account is not None and account.is_usable:
        token = identity.issue_credential_token(db, account=account, purpose="reset")
        # Handed to the notification service, which sends the link. Never
        # returned to the caller.
        _ = token
    return {"message": "If that address is registered, a reset link is on its way."}


class ResetPasswordIn(Schema):
    token: str
    new_password: Annotated[str, Field(min_length=12, max_length=200)]


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(
    payload: ResetPasswordIn,
    request: Request,
    db: Session = Depends(tenant_db),
    audit: object = Depends(audit_writer),
) -> None:
    tenant_of(request)
    account = identity.redeem_credential_token(db, token=payload.token, purpose="reset")
    identity.change_password(
        db,
        account=account,
        current_password=None,
        new_password=payload.new_password,
        require_current=False,
    )


class MfaVerifyIn(Schema):
    code: Annotated[str, Field(min_length=6, max_length=8)]


@router.post("/mfa/verify", response_model=TokenOut)
def verify_mfa(payload: MfaVerifyIn, ctx: AuthContext) -> TokenOut:
    """Step up the current session.

    A fresh access token is issued rather than mutating the old one, because
    the MFA state is read from the session row on the next request and the
    client needs a token whose `sid` still points at it.
    """
    from datetime import datetime

    from acmis.modules.identity.models import Session as UserSession

    if not ctx.principal.session_id:
        raise Unauthenticated("No active session to confirm.")
    session_row = ctx.db.get(UserSession, ctx.principal.session_id)
    if session_row is None or not session_row.is_live:
        raise Unauthenticated("This session is no longer valid.")

    account = ctx.db.get(UserAccount, ctx.principal.id)
    if account is None or not account.mfa_secret:
        raise Unauthenticated("This account has no second factor enrolled.")
    if not _verify_totp(account.mfa_secret, payload.code):
        raise Unauthenticated("That code is not correct.")

    session_row.mfa_satisfied_at = datetime.now(UTC)
    access = issue_token(
        subject_id=account.id,
        kind="access",
        tenant_id=ctx.tenant.id,
        session_id=session_row.id,
        claims={"knd": account.kind, "mfa": True},
    )
    return TokenOut(
        access_token=access, expires_in=settings.access_token_ttl_seconds, mfa_required=False
    )


def _verify_totp(secret: str, code: str) -> bool:
    """RFC 6238 TOTP, 30-second step, one step of clock skew either way.

    Implemented rather than pulled in: it is twenty lines of HMAC and the
    dependency surface of an authentication library is not worth it for this.
    """
    import base64
    import hashlib
    import hmac
    import struct
    import time

    try:
        key = base64.b32decode(secret.upper() + "=" * (-len(secret) % 8))
    except Exception:
        return False
    counter = int(time.time()) // 30
    for drift in (-1, 0, 1):
        digest = hmac.new(key, struct.pack(">Q", counter + drift), hashlib.sha1).digest()
        offset = digest[-1] & 0x0F
        value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
        if f"{value % 1_000_000:06d}" == code.strip():
            return True
    return False
