"""The request context: who is asking, on behalf of which university.

Held in a `ContextVar` rather than passed down every call because the audit
writer and the policy engine sit at the bottom of the stack and must not
require every service method in between to thread a principal through its
signature — the one place that forgets is the one place that writes an
unattributed change to a student's marks.

`ContextVar` is correct for both execution models FastAPI uses: an async
endpoint gets its own context per task, and a sync endpoint runs in a
threadpool worker where the context is copied in. A module-level global would
be shared across concurrent requests and leak one university's identity into
another's transaction.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Any, Literal

PrincipalKind = Literal["staff", "student", "applicant", "service", "platform", "anonymous"]


@dataclass(frozen=True, slots=True)
class TenantContext:
    """The university this request belongs to."""

    id: uuid.UUID
    slug: str
    name: str
    database: str
    dsn: str
    locale: str = "en-UG"
    timezone: str = "Africa/Kampala"
    currency: str = "UGX"
    features: frozenset[str] = field(default_factory=frozenset)
    settings: dict[str, Any] = field(default_factory=dict)

    def has_feature(self, name: str) -> bool:
        return name in self.features


@dataclass(frozen=True, slots=True)
class Principal:
    """The authenticated actor, flattened into the attributes ABAC needs.

    Assembled once at authentication time. The policy engine reads only this —
    it never queries the database — so an authorization decision costs no I/O
    and cannot be affected by a change committed mid-request.

    `scopes` are what an *OAuth client* was granted; `permissions` are what the
    actor's roles grant. A request is limited by the intersection: a developer
    portal token with `results:read` acting for a registrar who cannot see
    another faculty's marks still cannot see them.
    """

    id: uuid.UUID
    kind: PrincipalKind
    display_name: str
    email: str | None = None
    tenant_id: uuid.UUID | None = None
    #: Role codes, e.g. {"registrar", "faculty_dean"}.
    roles: frozenset[str] = field(default_factory=frozenset)
    #: Flattened permission codes, e.g. {"results:approve", "student:read"}.
    permissions: frozenset[str] = field(default_factory=frozenset)
    #: OAuth scopes when the call arrives through the developer portal.
    scopes: frozenset[str] = field(default_factory=frozenset)
    #: Organisational reach — the faculties/departments/programmes the actor is
    #: attached to. Policies compare these against the resource's own unit.
    faculty_ids: frozenset[uuid.UUID] = field(default_factory=frozenset)
    department_ids: frozenset[uuid.UUID] = field(default_factory=frozenset)
    programme_ids: frozenset[uuid.UUID] = field(default_factory=frozenset)
    #: For students: their own record id, so `subject.student_id == resource.student_id`
    #: is expressible without a lookup.
    student_id: uuid.UUID | None = None
    applicant_id: uuid.UUID | None = None
    staff_id: uuid.UUID | None = None
    #: True once the session has cleared MFA. Policies on high-risk actions
    #: (award conferment, fee waiver, bulk export) require it.
    mfa_satisfied: bool = False
    #: Platform staff acting inside a tenant. Every decision made while this is
    #: set is written to the audit trail with the impersonator recorded.
    impersonator_id: uuid.UUID | None = None
    session_id: uuid.UUID | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def is_anonymous(self) -> bool:
        return self.kind == "anonymous"

    @property
    def is_platform(self) -> bool:
        return self.kind == "platform"

    def attributes(self) -> dict[str, Any]:
        """Flatten into the shape policy conditions are written against."""
        return {
            "id": str(self.id),
            "kind": self.kind,
            "roles": sorted(self.roles),
            "permissions": sorted(self.permissions),
            "scopes": sorted(self.scopes),
            "faculty_ids": sorted(str(i) for i in self.faculty_ids),
            "department_ids": sorted(str(i) for i in self.department_ids),
            "programme_ids": sorted(str(i) for i in self.programme_ids),
            "student_id": str(self.student_id) if self.student_id else None,
            "applicant_id": str(self.applicant_id) if self.applicant_id else None,
            "staff_id": str(self.staff_id) if self.staff_id else None,
            "mfa_satisfied": self.mfa_satisfied,
            "is_impersonated": self.impersonator_id is not None,
            "tenant_id": str(self.tenant_id) if self.tenant_id else None,
            **self.extra,
        }


ANONYMOUS = Principal(id=uuid.UUID(int=0), kind="anonymous", display_name="anonymous")


@dataclass(frozen=True, slots=True)
class RequestContext:
    request_id: uuid.UUID
    principal: Principal
    tenant: TenantContext | None
    #: Client-observable facts policies may condition on — an examiner may
    #: enter marks only from inside the campus network, say.
    ip_address: str | None = None
    user_agent: str | None = None
    method: str = ""
    path: str = ""
    #: Which module app originated the call, from the `X-ACMIS-Module` header.
    #: Recorded in the audit trail so "who changed this" also answers "from
    #: where", and lets a policy forbid mark entry from the public portal.
    module: str | None = None

    def environment(self) -> dict[str, Any]:
        return {
            "ip_address": self.ip_address,
            "module": self.module,
            "method": self.method,
            "path": self.path,
            "request_id": str(self.request_id),
        }


@dataclass(slots=True)
class _Holder:
    """A mutable box around the request context.

    The indirection is load-bearing, and the reason is subtle enough to be
    worth stating plainly.

    FastAPI runs a *synchronous* dependency or endpoint in a threadpool, and
    each `run_in_threadpool` call executes with a **copy** of the caller's
    context. So a `ContextVar.set()` performed inside one sync dependency is
    invisible to the endpoint that follows it — they are different context
    copies. The first version of this module set the ContextVar from the
    authentication dependency, and every authorization decision downstream saw
    the anonymous principal the middleware had installed. Everything was
    correctly denied by default, which is exactly the failure mode that looks
    like a policy bug and is not.

    A copied context still carries the *same object* a ContextVar points at.
    So the middleware — which runs in the outer async context, above every
    threadpool hop — sets the holder once, and a dependency mutates the
    holder's field. Every copy sees the mutation because they all reference
    one box.
    """

    context: RequestContext


_holder: ContextVar[_Holder | None] = ContextVar("acmis_request_holder", default=None)


def current_context() -> RequestContext | None:
    holder = _holder.get()
    return holder.context if holder is not None else None


def require_context() -> RequestContext:
    ctx = current_context()
    if ctx is None:  # pragma: no cover - a bug, not a runtime condition
        raise RuntimeError(
            "No ACMIS request context. Anything that reads tenant or principal "
            "must run inside the middleware, or inside `use_context()` for jobs."
        )
    return ctx


def current_principal() -> Principal:
    ctx = current_context()
    return ctx.principal if ctx else ANONYMOUS


def current_tenant() -> TenantContext | None:
    ctx = current_context()
    return ctx.tenant if ctx else None


def set_context(ctx: RequestContext) -> Token[_Holder | None]:
    """Install a fresh holder. Call this from middleware or a job, once."""
    return _holder.set(_Holder(context=ctx))


def replace_context(ctx: RequestContext) -> None:
    """Update the context in place, so every threadpool copy sees the change.

    What authentication uses: the middleware installed an anonymous context
    before the route was matched, and the auth dependency swaps in the
    resolved principal. Mutating the shared holder is what makes that visible
    to the endpoint — see the note on `_Holder`.

    Falls back to installing a holder when there is none, so a job that
    forgets `use_context` degrades to working rather than to a silent
    anonymous principal.
    """
    holder = _holder.get()
    if holder is None:
        set_context(ctx)
    else:
        holder.context = ctx


def reset_context(token: Token[_Holder | None]) -> None:
    _holder.reset(token)


@contextmanager
def use_context(ctx: RequestContext) -> Iterator[RequestContext]:
    """Run a block under an explicit context — background jobs, CLI, tests.

    A nightly progression job still needs a principal, because the marks it
    writes must be attributable to something. It runs as a `service` principal
    whose name says which job it was.
    """
    token = set_context(ctx)
    try:
        yield ctx
    finally:
        reset_context(token)


def service_principal(name: str, tenant_id: uuid.UUID | None = None) -> Principal:
    """A named non-human actor, so automated changes are still attributable."""
    return Principal(
        id=uuid.uuid5(uuid.NAMESPACE_URL, f"acmis:service:{name}"),
        kind="service",
        display_name=f"service:{name}",
        tenant_id=tenant_id,
        roles=frozenset({"service"}),
        mfa_satisfied=True,
    )
