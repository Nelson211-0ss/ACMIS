"""HTTP surface, assembled.

One router per module, mounted under `/api/v1`. Tags match the module names so
the generated OpenAPI document — and therefore the generated TypeScript client
in `packages/api-client` — is split along the same lines as the frontend apps.
"""

from fastapi import APIRouter

from acmis.routers import (
    admissions,
    assessment,
    auth,
    authz,
    curriculum,
    developers,
    elections,
    finance,
    governance,
    learning,
    library,
    lifecycle,
    people,
    platform,
    public,
    quality,
    shared,
    students,
)

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(authz.router)
api_router.include_router(shared.router)
api_router.include_router(admissions.router)
api_router.include_router(students.router)
api_router.include_router(curriculum.router)
api_router.include_router(finance.router)
api_router.include_router(people.router)
api_router.include_router(assessment.router)
api_router.include_router(learning.router)
api_router.include_router(lifecycle.router)
api_router.include_router(library.router)
api_router.include_router(quality.router)
api_router.include_router(governance.router)
api_router.include_router(developers.router)
api_router.include_router(elections.router)
api_router.include_router(platform.router)
api_router.include_router(public.router)

# `interop` is deliberately absent: the standards endpoints mount at the app
# root (`/ims/...`, `/lti/...`) rather than under `/api/v1`, so `acmis.main`
# includes that router directly. See the note there.
__all__ = ["api_router"]
