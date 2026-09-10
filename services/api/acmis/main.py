"""The ACMIS API — one process, every module, every tenant.

Why a monolith. Nine frontend apps talk to one backend, and the reflex would be
nine services. It would be the wrong call here, for reasons specific to this
domain rather than general distaste for microservices:

* **The transactions cross modules.** Enrolling an admitted applicant creates a
  student, an enrolment, an invoice and an audit trail, and either all four
  happen or none do. Across services that becomes a saga with compensating
  actions, and the compensating action for "a student record was created" is
  not something anyone wants to write.
* **Authorization needs the whole picture.** A decision reads the actor's
  roles, their faculties, the resource's department and the semester's dates.
  Assembling that across service boundaries means either chatty calls on the
  hot path or duplicated data that goes stale — and a stale authorization
  attribute is a security bug.
* **The audit trail must be atomic with the change.** See `core.audit`.
* **The operators are small teams.** A university's ICT directorate has a
  handful of people. One deployable that can be reasoned about beats nine that
  cannot.

What keeps it from rotting: `acmis/modules/` are strict boundaries, tested in
`tests/test_module_boundaries.py`. Modules talk through service functions, not
each other's tables. If one genuinely needs to be extracted later, the seam is
already drawn.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, ORJSONResponse
from sqlalchemy import text

from acmis import __version__
from acmis.core.abac.registry import registry
from acmis.core.config import settings
from acmis.core.db import control_engine, dispose_all_engines, live_tenant_engines
from acmis.core.errors import ACMISError
from acmis.core.logging import configure_logging
from acmis.core.middleware import (
    ErrorMiddleware,
    RateLimitMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
    TenantMiddleware,
)
from acmis.modules.registry import configure as configure_mappers
from acmis.routers import api_router
from acmis.routers.interop import router as interop_router

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    configure_logging()

    # Importing this registers every resource descriptor. Done at startup so a
    # missing one is a boot failure rather than a 500 on the endpoint nobody
    # exercised in staging.
    import acmis.modules.descriptors  # noqa: F401

    # And resolves every mapper, including the relationships that cross a
    # module boundary by name. A name that cannot be resolved fails here,
    # with the mapper reported, rather than inside the first request that
    # happens to traverse it. See `acmis.modules.registry`.
    configure_mappers()

    # A policy bundle that will not load stops the process. Serving requests
    # with less authorization than the deployment declares is worse than not
    # serving them: the first is a silent breach, the second is an outage
    # somebody fixes in ten minutes.
    registry.load_builtin()

    engine = registry.default_engine()
    problems = engine.lint()
    log.info(
        "acmis_started",
        version=__version__,
        environment=settings.environment,
        policies=len(engine.policies),
        bundle=engine.version,
        lint_problems=len(problems),
    )
    if problems:
        log.warning("policy_lint_problems", problems=problems)

    yield

    dispose_all_engines()
    log.info("acmis_stopped")


app = FastAPI(
    title="ACMIS API",
    description=(
        "Academic Management Information System — multi-tenant, module-complete.\n\n"
        "Every request resolves to exactly one institution, and every action is "
        "checked against that institution's ABAC policy bundle and recorded in its "
        "audit trail."
    ),
    version=__version__,
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
    openapi_url="/openapi.json",
)

# Middleware is applied bottom-up by Starlette: the last one added is the
# outermost. So this list reads inside-out, and the order asserted in
# `tests/test_middleware_order.py` is the reverse of this block.
app.add_middleware(RateLimitMiddleware)
app.add_middleware(TenantMiddleware)
app.add_middleware(ErrorMiddleware)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=[
        "authorization",
        "content-type",
        "x-acmis-tenant",
        "x-acmis-module",
        "x-acmis-api-key",
        "x-request-id",
        "if-match",
    ],
    expose_headers=["x-request-id", "x-acmis-tenant", "server-timing", "etag"],
    max_age=600,
)

app.include_router(api_router, prefix=settings.api_prefix)

# Standards endpoints mount at the root, not under the API prefix. A
# conforming OneRoster consumer constructs
# `/ims/oneroster/rostering/v1p2/users` and an LTI tool is configured with a
# JWKS URL — putting either behind our own prefix means every client has to be
# told about us, which is precisely what standards exist to avoid.
app.include_router(interop_router)


@app.exception_handler(ACMISError)
async def _domain_error(_request: Request, exc: ACMISError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error": exc.to_payload()})


@app.exception_handler(RequestValidationError)
async def _validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
    """Reshape FastAPI's validation errors into the standard envelope.

    Field paths are flattened to dotted names so the frontend can attach an
    error to a form field without walking a `loc` array.
    """
    fields: dict[str, list[str]] = {}
    for error in exc.errors():
        location = ".".join(str(p) for p in error["loc"] if p not in {"body", "query", "path"})
        fields.setdefault(location or "_", []).append(error["msg"])
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_failed",
                "message": "Some fields need attention.",
                "details": {"fields": fields},
            }
        },
    )


@app.get("/health/live", tags=["health"], include_in_schema=False)
def live() -> dict[str, str]:
    """Liveness. Answers without touching a database on purpose.

    A liveness probe that queries Postgres restarts the API when the database
    hiccups, which turns a brief database blip into a rolling restart of every
    replica.
    """
    return {"status": "ok", "version": __version__}


@app.get("/health/ready", tags=["health"], include_in_schema=False)
def ready() -> dict[str, Any]:
    """Readiness. This one does check its dependencies."""
    checks: dict[str, Any] = {"control_database": "unknown", "policies": "unknown"}
    healthy = True

    try:
        with control_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["control_database"] = "ok"
    except Exception as exc:
        checks["control_database"] = f"error: {type(exc).__name__}"
        healthy = False

    try:
        engine = registry.default_engine()
        checks["policies"] = {
            "count": len(engine.policies),
            "bundle": engine.version,
            "lint": engine.lint() or "clean",
        }
    except Exception as exc:
        checks["policies"] = f"error: {exc}"
        healthy = False

    checks["tenant_engines_live"] = live_tenant_engines()
    return {"status": "ok" if healthy else "degraded", "checks": checks}


@app.get("/health", tags=["health"], include_in_schema=False)
def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name, "version": __version__}
