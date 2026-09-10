"""Passwords, tokens and the small primitives every module trusts.

Argon2id for passwords, HS256 JWTs for sessions. Deliberately boring choices:
this is the one part of the system where inventing something is a bad idea.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from argon2.low_level import Type
from jose import JWTError, jwt

from acmis.core.config import settings
from acmis.core.errors import Unauthenticated

TokenKind = Literal["access", "refresh", "reset", "invite", "verify", "impersonation"]

_hasher = PasswordHasher(
    time_cost=settings.argon2_time_cost,
    memory_cost=settings.argon2_memory_cost_kib,
    parallelism=settings.argon2_parallelism,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)


def hash_password(password: str) -> str:
    """Argon2id, with the cost parameters embedded in the hash string.

    Storing the parameters alongside the digest is what makes raising the cost
    later possible: an old hash still verifies under its own parameters, and
    `needs_rehash` tells us to upgrade it on the next successful sign-in.
    """
    return _hasher.hash(password.strip().encode("utf-8").decode("utf-8"))


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, password)
    except (VerifyMismatchError, InvalidHashError, ValueError):
        return False


def needs_rehash(hashed: str) -> bool:
    try:
        return _hasher.check_needs_rehash(hashed)
    except (InvalidHashError, ValueError):
        return True


def password_problems(password: str, *, context: list[str] | None = None) -> list[str]:
    """Composition checks, deliberately light on rules and heavy on length.

    No forced symbol classes. NIST dropped them because they push people
    towards `Password1!` — predictable to a cracker, painful for the registry
    clerk who has to type it forty times a day. Length and a denylist of the
    obvious institutional guesses do more.
    """
    problems: list[str] = []
    if len(password) < settings.password_min_length:
        problems.append(f"Use at least {settings.password_min_length} characters.")
    if password.lower() in _COMMON_PASSWORDS:
        problems.append("That password is too common.")
    lowered = password.lower()
    for token in context or []:
        if len(token) >= 4 and token.lower() in lowered:
            problems.append("Do not include your name, email or student number.")
            break
    if len(set(password)) < 5:
        problems.append("Use a greater variety of characters.")
    return problems


_COMMON_PASSWORDS = frozenset(
    {
        "password",
        "password1",
        "password123",
        "12345678",
        "123456789",
        "qwertyuiop",
        "letmein123",
        "admin12345",
        "student123",
        "makerere",
        "university",
        "changeme123",
        "acmis1234",
        "welcome123",
    }
)


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------


def issue_token(
    *,
    subject_id: uuid.UUID,
    kind: TokenKind,
    tenant_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
    ttl_seconds: int | None = None,
    claims: dict[str, Any] | None = None,
) -> str:
    """Mint a signed token.

    `tid` (tenant) is a claim rather than something taken from the request,
    because the alternative — trusting a `X-Tenant` header alongside a valid
    token — lets a signed-in user at one university address another's database
    by editing a header. The claim is what the middleware believes, and a
    mismatch between claim and host is refused rather than reconciled.
    """
    now = datetime.now(UTC)
    ttl = ttl_seconds or _default_ttl(kind)
    payload: dict[str, Any] = {
        "sub": str(subject_id),
        "typ": kind,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl)).timestamp()),
        "jti": str(uuid.uuid4()),
        "iss": settings.service_name,
    }
    if tenant_id:
        payload["tid"] = str(tenant_id)
    if session_id:
        payload["sid"] = str(session_id)
    if claims:
        payload |= claims
    token: str = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token


def _default_ttl(kind: TokenKind) -> int:
    return {
        "access": settings.access_token_ttl_seconds,
        "refresh": settings.refresh_token_ttl_seconds,
        "reset": 3600,
        "verify": 48 * 3600,
        "invite": 14 * 24 * 3600,
        # Support sessions are short on purpose: a forgotten impersonation
        # window is an open door into a university's records.
        "impersonation": 30 * 60,
    }[kind]


def read_token(token: str, *, expect: TokenKind | None = None) -> dict[str, Any]:
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub", "typ"]},
        )
    except JWTError as exc:
        raise Unauthenticated("Your session is not valid. Sign in again.") from exc
    if expect and payload.get("typ") != expect:
        # A refresh token presented as an access token is either a bug or an
        # attempt; either way it must not be honoured, because refresh tokens
        # live for two weeks and access tokens for fifteen minutes.
        raise Unauthenticated("Wrong kind of token for this request.")
    return payload


# ---------------------------------------------------------------------------
# Opaque secrets: API keys, reset codes, webhook signatures
# ---------------------------------------------------------------------------

API_KEY_PREFIX_LENGTH = 8


def new_api_key(*, environment: str = "live") -> tuple[str, str, str]:
    """Return (full_key, prefix, hash).

    Shape is `acmis_live_<prefix>_<secret>`. The prefix is stored in clear so
    the console can show which key is which and so a leaked key found in a
    public repository can be identified and revoked without its holder having
    to tell us. Only the hash of the whole key is stored.
    """
    prefix = secrets.token_hex(API_KEY_PREFIX_LENGTH // 2)
    secret = secrets.token_urlsafe(32)
    full = f"acmis_{environment}_{prefix}_{secret}"
    return full, prefix, hash_secret(full)


def hash_secret(value: str) -> str:
    """SHA-256, not Argon2.

    Argon2 is for low-entropy human passwords. An API key is 256 bits of
    randomness, so there is nothing to brute-force and a memory-hard hash
    would only add 100ms to every machine request.
    """
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def sign_webhook(payload: bytes, secret: str, *, timestamp: int) -> str:
    """Timestamped HMAC, in the `t=…,v1=…` form Stripe popularised.

    The timestamp is inside the signed material so a captured delivery cannot
    be replayed a week later; receivers are told to reject anything older than
    five minutes.
    """
    material = f"{timestamp}.".encode() + payload
    digest = hmac.new(secret.encode("utf-8"), material, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


def numeric_code(length: int = 6) -> str:
    """A code that will be read down a phone line to a student in a village.

    Digits only, and generated with `secrets` — a 6-digit OTP from
    `random.randint` is guessable given a couple of observed values.
    """
    return "".join(secrets.choice("0123456789") for _ in range(length))


def token_urlsafe(length: int = 32) -> str:
    return secrets.token_urlsafe(length)
