"""Request middleware: context, tenant, audit, rate limiting, errors.

Order matters and is asserted in `tests/test_middleware_order.py`. Outermost
first:

1. `RequestContextMiddleware` — assigns the request id and builds the context.
   Everything below it can log with correlation.
2. `ErrorMiddleware` — turns exceptions into the standard error envelope.
   Inside the context so a 500 is still attributable to a tenant and actor.
3. `TenantMiddleware` — resolves the university and attaches the policy engine.
4. `RateLimitMiddleware` — per-tenant and per-principal, so one university
   cannot exhaust the budget of another.
5. `AuditMiddleware` — innermost, holding the writer that endpoints emit into
   and flushing it in the endpoint's own transaction.

Authentication is *not* middleware. It is a dependency, because a route has to
be able to declare that it is public (certificate verification, the sign-in
endpoint itself) and middleware cannot see route metadata before matching.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from acmis.core import tenant_resolver
from acmis.core.abac.registry import registry
from acmis.core.config import settings
from acmis.core.context import (
    ANONYMOUS,
    RequestContext,
    reset_context,
    set_context,
)
from acmis.core.db import ControlSessionLocal
from acmis.core.errors import ACMISError, Conflict, RateLimited
from acmis.core.security import read_token

log = structlog.get_logger(__name__)

Next = Callable[[Request], Awaitable[Response]]

#: Paths that never need a tenant or a principal.
OPEN_PATHS = frozenset(
    {
        "/health",
        "/health/ready",
        "/health/live",
        "/metrics",
        "/openapi.json",
        "/docs",
        "/docs/oauth2-redirect",
        "/redoc",
    }
)


class RequestContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Next) -> Response:
        # Honour an inbound request id so a trace spans the Next.js BFF and the
        # API. Validated as a UUID rather than trusted: it is echoed into logs
        # and an unvalidated header is a log-injection vector.
        incoming = request.headers.get("x-request-id")
        try:
            request_id = uuid.UUID(incoming) if incoming else uuid.uuid4()
        except ValueError:
            request_id = uuid.uuid4()

        ctx = RequestContext(
            request_id=request_id,
            principal=ANONYMOUS,
            tenant=None,
            ip_address=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
            method=request.method,
            path=request.url.path,
            module=request.headers.get("x-acmis-module"),
        )
        token = set_context(ctx)
        request.state.acmis_context = ctx
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            reset_context(token)
        elapsed_ms = (time.perf_counter() - started) * 1000
        response.headers["x-request-id"] = str(request_id)
        response.headers["server-timing"] = f"app;dur={elapsed_ms:.1f}"
        if request.url.path not in OPEN_PATHS:
            log.info(
                "request",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                duration_ms=round(elapsed_ms, 1),
            )
        return response


def _client_ip(request: Request) -> str | None:
    """Real client address behind a proxy.

    `X-Forwarded-For` is a list the client can prepend to, so only the
    right-most hop added by our own ingress is trustworthy. Policies condition
    on this (mark entry from inside the campus network), which makes getting it
    wrong an authorization bug and not just a logging one.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded and settings.environment != "local":
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else None


#: Postgres constraint names mapped to what a person did wrong. The generic
#: message is a fallback, not the intent: "a question bank with this code
#: already exists" is actionable, and "something went wrong" is not.
_CONSTRAINT_MESSAGES = {
    "uq_question_bank_code": "A question bank with this code already exists.",
    "uq_response_question": "That question has already been answered in this attempt.",
    "uq_attempt_number": "This candidate already has an attempt with that number.",
}


def _integrity_conflict(exc: IntegrityError) -> Conflict:
    """Turn a constraint violation into the 409 it actually is.

    A unique or foreign-key violation is the database enforcing a rule the
    request broke — a duplicate code, a reference to something deleted. That is
    a 409, not a 500: a 500 says the server is broken and tells the caller to
    contact support about their own typo. The constraint *name* is safe to
    branch on; the driver's message is not returned, because it quotes the
    offending values and the schema.
    """
    original = getattr(exc, "orig", None)
    diagnostic = getattr(original, "diag", None)
    constraint = getattr(diagnostic, "constraint_name", None) or ""
    message = _CONSTRAINT_MESSAGES.get(constraint)
    if message is None:
        if constraint.startswith(("uq_", "ix_uq_")) or "unique" in constraint:
            message = "One of these values is already in use."
        elif constraint.startswith("fk_"):
            message = "That refers to a record which no longer exists."
        elif constraint.startswith("ck_"):
            message = "One of these values is not allowed."
        else:
            message = Conflict.message
    return Conflict(message, details={"constraint": constraint} if constraint else None)


class ErrorMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Next) -> Response:
        try:
            return await call_next(request)
        except ACMISError as exc:
            log.info("domain_error", code=exc.code, status=exc.status_code, path=request.url.path)
            return JSONResponse(status_code=exc.status_code, content={"error": exc.to_payload()})
        except IntegrityError as exc:
            conflict = _integrity_conflict(exc)
            log.info(
                "integrity_conflict",
                constraint=conflict.details.get("constraint"),
                path=request.url.path,
            )
            return JSONResponse(
                status_code=conflict.status_code, content={"error": conflict.to_payload()}
            )
        except Exception:
            # The message is deliberately fixed. A traceback or an ORM error
            # string in the response body tells an attacker the schema, and
            # tells a student nothing useful.
            log.exception("unhandled_error", path=request.url.path)
            return JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "code": "internal_error",
                        "message": "Something went wrong. The reference below will help support.",
                        "details": {
                            "request_id": request.headers.get("x-request-id")
                            or str(
                                getattr(request.state, "acmis_context", None)
                                and request.state.acmis_context.request_id
                            )
                        },
                    }
                },
            )


class TenantMiddleware(BaseHTTPMiddleware):
    """Resolves the tenant and swaps it into the context."""

    async def dispatch(self, request: Request, call_next: Next) -> Response:
        if request.url.path in OPEN_PATHS:
            return await call_next(request)

        ctx: RequestContext = request.state.acmis_context
        token_tenant_id: uuid.UUID | None = None

        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            try:
                claims = read_token(auth[7:], expect="access")
                if claims.get("tid"):
                    token_tenant_id = uuid.UUID(str(claims["tid"]))
            except Exception:
                # An unreadable token is not this middleware's problem — the
                # authentication dependency will reject it with a proper 401.
                # Here it simply contributes no tenant.
                token_tenant_id = None

        session = ControlSessionLocal()
        try:
            resolved = tenant_resolver.resolve_from_request(
                session,
                host=request.headers.get("host"),
                token_tenant_id=token_tenant_id,
                header_slug=request.headers.get("x-acmis-tenant"),
            )
        finally:
            session.close()

        if resolved is None:
            request.state.acmis_policy_engine = registry.default_engine()
            return await call_next(request)

        tenant, policy_revision = resolved
        new_ctx = RequestContext(
            request_id=ctx.request_id,
            principal=ctx.principal,
            tenant=tenant,
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
            method=ctx.method,
            path=ctx.path,
            module=ctx.module,
        )
        request.state.acmis_context = new_ctx
        request.state.acmis_policy_revision = policy_revision
        # A fresh holder, installed from the outer async context so every
        # threadpool hop below inherits a reference to it. The authentication
        # dependency later mutates this same holder rather than replacing it.
        token = set_context(new_ctx)
        try:
            response = await call_next(request)
        finally:
            reset_context(token)
        response.headers["x-acmis-tenant"] = tenant.slug
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Token bucket, per (tenant, principal-or-ip).

    In-process by default, which is honest rather than ideal: with N replicas
    the effective limit is N times the configured one. Set `ACMIS_REDIS_URL`
    and the bucket moves to Redis, which is what a real deployment does. The
    in-process version is here because a rate limiter that only works with
    Redis is a rate limiter that is switched off in development, and then the
    first time anyone exercises it is in production.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self._buckets: dict[str, tuple[float, float]] = {}

    async def dispatch(self, request: Request, call_next: Next) -> Response:
        if not settings.rate_limit_enabled or request.url.path in OPEN_PATHS:
            return await call_next(request)

        ctx: RequestContext = request.state.acmis_context
        identity = (
            f"{ctx.tenant.slug if ctx.tenant else '-'}:"
            f"{ctx.principal.id if not ctx.principal.is_anonymous else ctx.ip_address}"
        )
        if not self._allow(identity):
            log.warning("rate_limited", identity=identity, path=request.url.path)
            exc = RateLimited()
            return JSONResponse(
                status_code=exc.status_code,
                content={"error": exc.to_payload()},
                headers={"retry-after": "10"},
            )
        return await call_next(request)

    def _allow(self, identity: str) -> bool:
        now = time.monotonic()
        capacity = float(settings.rate_limit_burst)
        refill_per_second = settings.rate_limit_per_minute / 60.0
        tokens, last = self._buckets.get(identity, (capacity, now))
        tokens = min(capacity, tokens + (now - last) * refill_per_second)
        if tokens < 1.0:
            self._buckets[identity] = (tokens, now)
            return False
        self._buckets[identity] = (tokens - 1.0, now)
        if len(self._buckets) > 50_000:  # crude ceiling; Redis has no such need
            self._buckets.clear()
        return True


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Next) -> Response:
        response = await call_next(request)
        response.headers.setdefault("x-content-type-options", "nosniff")
        response.headers.setdefault("x-frame-options", "DENY")
        response.headers.setdefault("referrer-policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "permissions-policy", "geolocation=(), microphone=(), camera=()"
        )
        if settings.is_production:
            response.headers.setdefault(
                "strict-transport-security", "max-age=63072000; includeSubDomains"
            )
        return response
