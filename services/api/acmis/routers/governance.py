"""Governance, reporting and audit endpoints."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, status
from pydantic import Field
from sqlalchemy import func, select

from acmis.core.abac import authorize
from acmis.core.abac.policy import Policy
from acmis.core.abac.registry import registry
from acmis.core.audit import AuditCategory, emit
from acmis.core.deps import AnyContext, PageQuery, StaffContext
from acmis.core.errors import Conflict, RuleViolation, ValidationFailed
from acmis.core.models import utcnow
from acmis.core.pagination import keyset_page
from acmis.core.schemas import Page, Reason, Schema
from acmis.modules.governance.models import (
    AccessLog,
    AuditEvent,
    DataRequest,
    PolicyChangeLog,
    PolicyOverlay,
    ReportDefinition,
    ReportRun,
    StatutoryReturn,
)
from acmis.routers._common import get_or_404

router = APIRouter(prefix="/governance", tags=["governance"])


class AuditEventOut(Schema):
    id: uuid.UUID
    occurred_at: datetime
    request_id: uuid.UUID | None
    correlation_id: uuid.UUID | None
    actor_id: uuid.UUID | None
    actor_kind: str
    actor_label: str | None
    actor_roles: list[str]
    impersonator_id: uuid.UUID | None
    module: str | None
    action: str
    category: str
    outcome: str
    severity: str
    resource_type: str
    resource_id: str | None
    resource_label: str | None
    summary: str | None
    changes: list[dict[str, Any]]
    event_metadata: dict[str, Any]
    decision_policy_id: str | None
    decision_rule_id: str | None
    policy_bundle_version: str | None
    ip_address: str | None
    http_method: str | None
    http_path: str | None


@router.get("/audit", response_model=Page[AuditEventOut])
def search_audit(
    ctx: StaffContext,
    page: PageQuery,
    actor_id: uuid.UUID | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    student_id: uuid.UUID | None = None,
    category: str | None = None,
    outcome: str | None = None,
    action: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> Page[AuditEventOut]:
    """Search the audit trail. Reading it is itself audited.

    The read is recorded because an audit log only its subjects can see is not
    oversight, and one anyone can read is a directory of who has looked at
    whom. Recording the reader keeps both problems in view.
    """
    authorize(
        engine=ctx.engine,
        action="audit_event:search",
        resource_type="audit_event",
        resource={
            "id": None,
            "subject_student_id": str(student_id) if student_id else None,
            "category": category,
            "actor_id": str(actor_id) if actor_id else None,
        },
        category=AuditCategory.CONFIGURATION,
        audit_reads=True,
    )

    stmt = select(AuditEvent)
    if actor_id:
        stmt = stmt.where(AuditEvent.actor_id == actor_id)
    if resource_type:
        stmt = stmt.where(AuditEvent.resource_type == resource_type)
    if resource_id:
        stmt = stmt.where(AuditEvent.resource_id == resource_id)
    if student_id:
        stmt = stmt.where(AuditEvent.subject_student_id == student_id)
    if category:
        stmt = stmt.where(AuditEvent.category == category)
    if outcome:
        stmt = stmt.where(AuditEvent.outcome == outcome)
    if action:
        stmt = stmt.where(AuditEvent.action == action)
    if since:
        stmt = stmt.where(AuditEvent.occurred_at >= since)
    if until:
        stmt = stmt.where(AuditEvent.occurred_at <= until)

    found = keyset_page(
        ctx.db, stmt, page=page, key=AuditEvent.occurred_at, ident=AuditEvent.id, descending=True
    )
    return Page.of(
        [AuditEventOut.model_validate(r) for r in found.rows],
        limit=page.limit,
        next_cursor=found.next_cursor,
        total=found.total,
    )


@router.get("/audit/me", response_model=Page[AuditEventOut])
def my_audit_trail(ctx: AnyContext, page: PageQuery) -> Page[AuditEventOut]:
    """The trail of actions taken on the caller's own record.

    Granted by `governance.audit-access/own-trail`. A person being able to see
    who opened their file is the counterweight to staff being able to open it.
    """
    subject_filters = []
    if ctx.student_id:
        subject_filters.append(AuditEvent.subject_student_id == ctx.student_id)
    if ctx.principal.staff_id:
        subject_filters.append(AuditEvent.subject_staff_id == ctx.principal.staff_id)
    if not subject_filters:
        return Page.of([], limit=page.limit)

    authorize(
        engine=ctx.engine,
        action="audit_event:read",
        resource_type="audit_event",
        resource={
            "id": None,
            "subject_student_id": str(ctx.student_id) if ctx.student_id else None,
            "subject_staff_id": str(ctx.principal.staff_id) if ctx.principal.staff_id else None,
        },
    )
    from sqlalchemy import or_

    found = keyset_page(
        ctx.db,
        select(AuditEvent).where(or_(*subject_filters)),
        page=page,
        key=AuditEvent.occurred_at,
        ident=AuditEvent.id,
        descending=True,
    )
    return Page.of(
        [AuditEventOut.model_validate(r) for r in found.rows],
        limit=page.limit,
        next_cursor=found.next_cursor,
        total=found.total,
    )


@router.get("/audit/denials", response_model=dict)
def denial_summary(ctx: StaffContext, hours: int = 24) -> dict[str, Any]:
    """Recent authorization denials, grouped.

    The signal that matters most in an access review. One denial is a mis-set
    role; two hundred against different students in ten minutes is someone
    walking the record set. Grouping by actor and policy is what makes the
    difference visible.
    """
    authorize(
        engine=ctx.engine,
        action="audit_event:read",
        resource_type="audit_event",
        resource={"id": None, "category": "authorization"},
        category=AuditCategory.CONFIGURATION,
        audit_reads=True,
    )
    since = utcnow() - timedelta(hours=hours)

    by_actor = ctx.db.execute(
        select(
            AuditEvent.actor_id,
            AuditEvent.actor_label,
            func.count().label("denials"),
            func.count(func.distinct(AuditEvent.resource_id)).label("distinct_resources"),
        )
        .where(AuditEvent.outcome == "denied", AuditEvent.occurred_at >= since)
        .group_by(AuditEvent.actor_id, AuditEvent.actor_label)
        .order_by(func.count().desc())
        .limit(50)
    ).all()

    by_policy = ctx.db.execute(
        select(AuditEvent.decision_policy_id, AuditEvent.action, func.count())
        .where(AuditEvent.outcome == "denied", AuditEvent.occurred_at >= since)
        .group_by(AuditEvent.decision_policy_id, AuditEvent.action)
        .order_by(func.count().desc())
        .limit(50)
    ).all()

    return {
        "window_hours": hours,
        "by_actor": [
            {
                "actor_id": str(r.actor_id) if r.actor_id else None,
                "actor_label": r.actor_label,
                "denials": int(r.denials),
                "distinct_resources": int(r.distinct_resources),
                # The shape that distinguishes a confused user from a sweep.
                "looks_like_enumeration": int(r.distinct_resources) > 20,
            }
            for r in by_actor
        ],
        "by_policy": [
            {
                "policy": r[0] or "(denied by default)",
                "action": r[1],
                "denials": int(r[2]),
            }
            for r in by_policy
        ],
    }


class AccessLogOut(Schema):
    id: uuid.UUID
    occurred_at: datetime
    actor_id: uuid.UUID | None
    actor_label: str | None
    action: str
    resource_type: str
    resource_id: str | None
    subject_student_id: uuid.UUID | None
    fields_returned: list[str]
    fields_masked: list[str]
    record_count: int
    purpose: str | None
    ip_address: str | None


@router.get("/access-log", response_model=Page[AccessLogOut])
def search_access_log(
    ctx: StaffContext,
    page: PageQuery,
    student_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
) -> Page[AccessLogOut]:
    """Who looked at what. The data-protection question, separately answerable."""
    authorize(
        engine=ctx.engine,
        action="access_log:search",
        resource_type="access_log",
        resource={
            "id": None,
            "subject_student_id": str(student_id) if student_id else None,
            "actor_id": str(actor_id) if actor_id else None,
        },
        category=AuditCategory.CONFIGURATION,
        audit_reads=True,
    )
    stmt = select(AccessLog)
    if student_id:
        stmt = stmt.where(AccessLog.subject_student_id == student_id)
    if actor_id:
        stmt = stmt.where(AccessLog.actor_id == actor_id)
    found = keyset_page(
        ctx.db, stmt, page=page, key=AccessLog.occurred_at, ident=AccessLog.id, descending=True
    )
    return Page.of(
        [AccessLogOut.model_validate(r) for r in found.rows],
        limit=page.limit,
        next_cursor=found.next_cursor,
        total=found.total,
    )


# ---------------------------------------------------------------------------
# Policy administration
# ---------------------------------------------------------------------------


class PolicyOverlayOut(Schema):
    id: uuid.UUID
    policy_id: str
    description: str
    document: dict[str, Any]
    enabled: bool
    priority: int
    revision: int
    authored_by_id: uuid.UUID | None
    approved_by_id: uuid.UUID | None
    approved_at: datetime | None
    change_reason: str | None
    last_simulation: dict[str, Any]


class PolicyOverlayIn(Schema):
    policy_id: Annotated[str, Field(max_length=80, pattern=r"^[a-z][a-z0-9_.-]*$")]
    description: Annotated[str, Field(min_length=20, max_length=2000)]
    document: dict[str, Any]
    priority: Annotated[int, Field(ge=50, le=999)] = 100
    change_reason: Annotated[str, Field(min_length=10, max_length=2000)]


@router.get("/policies", response_model=list[PolicyOverlayOut])
def list_policies(ctx: StaffContext) -> list[PolicyOverlayOut]:
    authorize(
        engine=ctx.engine,
        action="policy:list",
        resource_type="policy",
        resource={"id": None, "enabled": True},
    )
    rows = (
        ctx.db.execute(
            select(PolicyOverlay)
            .where(PolicyOverlay.deleted_at.is_(None))
            .order_by(PolicyOverlay.priority, PolicyOverlay.policy_id)
        )
        .scalars()
        .all()
    )
    return [PolicyOverlayOut.model_validate(r) for r in rows]


@router.post("/policies", response_model=PolicyOverlayOut, status_code=status.HTTP_201_CREATED)
def create_policy(payload: PolicyOverlayIn, ctx: StaffContext) -> PolicyOverlayOut:
    """Author a tenant policy. Validated on save, disabled until enabled.

    Three refusals worth naming:

    * It must compile. A policy that fails to parse is rejected here rather
      than at the next request, where it would silently deny whatever it was
      meant to grant.
    * It may not collide with a builtin id. That is what stops "multi-tenant
      configurability" from meaning "any administrator can switch off
      separation of duties".
    * It arrives disabled. Enabling is a second, separate act after a
      simulation — the usual way to lock a university out of its own
      registration window is a deny rule that matched more than its author
      expected.
    """
    authorize(
        engine=ctx.engine,
        action="policy:create",
        resource_type="policy",
        resource={"id": None, "enabled": False, "priority": payload.priority},
        category=AuditCategory.CONFIGURATION,
    )

    if payload.policy_id in registry.builtin_ids:
        raise ValidationFailed(
            f"'{payload.policy_id}' is a built-in policy and cannot be replaced. "
            "Add a separate policy with its own id to tighten it.",
            code="builtin_policy_collision",
        )

    document = {**payload.document, "id": payload.policy_id, "priority": payload.priority}
    try:
        Policy.from_dict(document, source=f"tenant:{ctx.tenant.slug}")
    except Exception as exc:
        raise ValidationFailed(
            "This policy does not compile.", code="invalid_policy", details={"error": str(exc)}
        ) from exc

    existing = ctx.db.execute(
        select(PolicyOverlay).where(PolicyOverlay.policy_id == payload.policy_id)
    ).scalar_one_or_none()
    if existing is not None:
        raise Conflict(f"A policy with the id '{payload.policy_id}' already exists.")

    overlay = PolicyOverlay(
        policy_id=payload.policy_id,
        description=payload.description,
        document=document,
        enabled=False,
        priority=payload.priority,
        revision=1,
        authored_by_id=ctx.principal.id,
        change_reason=payload.change_reason,
        created_by_id=ctx.principal.id,
    )
    ctx.db.add(overlay)
    ctx.db.flush()
    ctx.db.add(
        PolicyChangeLog(
            policy_id=overlay.policy_id,
            revision=1,
            changed_by_id=ctx.principal.id,
            change_kind="created",
            document_after=document,
            reason=payload.change_reason,
        )
    )
    emit(
        "policy:create",
        AuditCategory.CONFIGURATION,
        resource_type="policy",
        resource_id=overlay.id,
        resource_label=overlay.policy_id,
        summary=f"Authored policy {overlay.policy_id} (disabled)",
        metadata={"reason": payload.change_reason, "priority": payload.priority},
        severity="warning",
    )
    return PolicyOverlayOut.model_validate(overlay)


class PolicyEnableIn(Reason):
    enabled: bool


@router.post("/policies/{overlay_id}/enable", response_model=PolicyOverlayOut)
def set_policy_enabled(
    overlay_id: uuid.UUID, payload: PolicyEnableIn, ctx: StaffContext
) -> PolicyOverlayOut:
    """Enable or disable a tenant policy, taking effect on the next request.

    The tenant's `policy_revision` is bumped in the control plane, which is
    what makes every replica pick up the change without a restart or a
    cache-invalidation message — the compiled bundle is keyed by that revision.
    """
    from acmis.core import tenant_resolver
    from acmis.core.db import ControlSessionLocal
    from acmis.modules.tenancy.models import Tenant

    overlay = get_or_404(ctx, PolicyOverlay, overlay_id)
    authorize(
        engine=ctx.engine,
        action="policy:update",
        resource_type="policy",
        resource=overlay,
        category=AuditCategory.CONFIGURATION,
    )
    if overlay.enabled == payload.enabled:
        return PolicyOverlayOut.model_validate(overlay)

    if payload.enabled and not overlay.last_simulation:
        raise RuleViolation(
            "Simulate this policy before enabling it. A deny rule that matches more "
            "than intended can lock the institution out of its own workflows.",
            rule="simulation_required",
            waivable_by=["policy:admin"],
        )

    before = overlay.enabled
    overlay.enabled = payload.enabled
    overlay.revision += 1
    overlay.approved_by_id = ctx.principal.id
    overlay.approved_at = utcnow()
    overlay.change_reason = payload.reason
    ctx.db.add(
        PolicyChangeLog(
            policy_id=overlay.policy_id,
            revision=overlay.revision,
            changed_by_id=ctx.principal.id,
            change_kind="enabled" if payload.enabled else "disabled",
            document_after=overlay.document,
            reason=payload.reason,
        )
    )
    ctx.db.flush()

    control = ControlSessionLocal()
    try:
        tenant = control.get(Tenant, ctx.tenant.id)
        if tenant is not None:
            tenant.policy_revision += 1
        control.commit()
    finally:
        control.close()
    registry.invalidate(ctx.tenant.id)
    tenant_resolver.invalidate(tenant_id=ctx.tenant.id, slug=ctx.tenant.slug)

    emit(
        "policy:update",
        AuditCategory.CONFIGURATION,
        resource_type="policy",
        resource_id=overlay.id,
        resource_label=overlay.policy_id,
        summary=f"Policy {'enabled' if payload.enabled else 'disabled'} (was {before})",
        metadata={"reason": payload.reason},
        severity="critical",
    )
    return PolicyOverlayOut.model_validate(overlay)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


class ReportDefinitionOut(Schema):
    id: uuid.UUID
    code: str
    name: str
    description: str | None
    kind: str
    module: str
    parameters: list[dict[str, Any]]
    required_permission: str | None
    contains_personal_data: bool
    schedule: str | None
    is_active: bool


@router.get("/reports", response_model=list[ReportDefinitionOut])
def list_reports(ctx: StaffContext, kind: str | None = None) -> list[ReportDefinitionOut]:
    authorize(
        engine=ctx.engine,
        action="report:list",
        resource_type="report",
        resource={"id": None, "kind": kind, "module": "governance"},
    )
    stmt = select(ReportDefinition).where(
        ReportDefinition.deleted_at.is_(None), ReportDefinition.is_active.is_(True)
    )
    if kind:
        stmt = stmt.where(ReportDefinition.kind == kind)
    rows = ctx.db.execute(stmt.order_by(ReportDefinition.name)).scalars().all()
    return [ReportDefinitionOut.model_validate(r) for r in rows]


class RunReportIn(Schema):
    parameters: dict[str, Any] = Field(default_factory=dict)
    output_format: Annotated[str, Field(pattern="^(xlsx|csv|pdf|json)$")] = "xlsx"
    #: Required for anything touching personal data —
    #: `governance.data-export` attaches a `require:reason` obligation.
    purpose: str | None = None


@router.post(
    "/reports/{definition_id}/run", response_model=dict, status_code=status.HTTP_202_ACCEPTED
)
def run_report(
    definition_id: uuid.UUID, ctx: StaffContext, payload: RunReportIn | None = None
) -> dict[str, Any]:
    """Queue a report run.

    A report over personal data is an export whether or not it is called one,
    so it is MFA-gated, needs a stated purpose, and its row count is recorded
    — that number is what an access review actually looks at.
    """
    body = payload or RunReportIn()
    definition = get_or_404(ctx, ReportDefinition, definition_id)
    decision = authorize(
        engine=ctx.engine,
        action="export:run" if definition.contains_personal_data else "report:run",
        resource_type="report_run",
        resource={
            "id": None,
            "definition_id": str(definition.id),
            "status": "queued",
            "requested_by_id": str(ctx.principal.id),
            "contains_personal_data": definition.contains_personal_data,
            "row_estimate": 0,
        },
        category=AuditCategory.DATA_EXPORT,
    )
    if "require:reason" in decision.obligations and not (body.purpose or "").strip():
        raise ValidationFailed(
            "State why this data is needed. The purpose is recorded with the export.",
            code="purpose_required",
        )

    run = ReportRun(
        definition_id=definition.id,
        parameters=body.parameters,
        status="queued",
        requested_by_id=ctx.principal.id,
        purpose=body.purpose,
        output_format=body.output_format,
        watermark=f"{ctx.principal.display_name} · {date.today():%Y-%m-%d}"
        if "watermark:recipient" in decision.obligations
        else None,
        # Exports expire. A file that lives forever in object storage is a copy
        # of the database with none of its access controls.
        expires_at=utcnow() + timedelta(days=7),
        created_by_id=ctx.principal.id,
    )
    ctx.db.add(run)
    ctx.db.flush()

    emit(
        "export:run" if definition.contains_personal_data else "report:run",
        AuditCategory.DATA_EXPORT,
        resource_type="report_run",
        resource_id=run.id,
        resource_label=definition.name,
        summary=f"{definition.name} queued ({body.output_format})",
        metadata={
            "purpose": body.purpose,
            "parameters": body.parameters,
            "personal_data": definition.contains_personal_data,
        },
        severity="warning" if definition.contains_personal_data else "info",
    )
    return {"run_id": str(run.id), "status": run.status, "expires_at": run.expires_at}


class StatutoryReturnOut(Schema):
    id: uuid.UUID
    code: str
    name: str
    regulator: str
    academic_year_id: uuid.UUID
    period_label: str
    due_on: date | None
    status: str
    validation_findings: list[dict[str, Any]]
    submitted_at: datetime | None
    acknowledgement_reference: str | None


@router.get("/statutory-returns", response_model=list[StatutoryReturnOut])
def list_statutory_returns(ctx: StaffContext) -> list[StatutoryReturnOut]:
    authorize(
        engine=ctx.engine,
        action="statutory_return:list",
        resource_type="statutory_return",
        resource={"id": None, "status": "draft", "regulator": "*"},
    )
    rows = (
        ctx.db.execute(
            select(StatutoryReturn)
            .where(StatutoryReturn.deleted_at.is_(None))
            .order_by(StatutoryReturn.due_on.asc().nullslast())
        )
        .scalars()
        .all()
    )
    return [StatutoryReturnOut.model_validate(r) for r in rows]


class DataRequestIn(Schema):
    kind: Annotated[str, Field(pattern="^(access|correction|erasure|portability|objection)$")]
    subject_student_id: uuid.UUID | None = None
    subject_staff_id: uuid.UUID | None = None
    subject_name: Annotated[str, Field(max_length=300)]
    description: Annotated[str, Field(min_length=10, max_length=4000)]


@router.post("/data-requests", response_model=dict, status_code=status.HTTP_201_CREATED)
def log_data_request(payload: DataRequestIn, ctx: StaffContext) -> dict[str, Any]:
    """Record a subject access, correction or erasure request.

    The statutory clock is external and enforceable, so the deadline is
    computed on creation rather than tracked by hand. 30 days is the common
    period across the jurisdictions ACMIS is built for; institutions with a
    shorter obligation override it in their settings.
    """
    import secrets

    authorize(
        engine=ctx.engine,
        action="data_request:create",
        resource_type="report",
        resource={"id": None, "kind": "statutory", "module": "governance"},
        category=AuditCategory.CONFIGURATION,
    )
    statutory_days = int(ctx.tenant.settings.get("data_request_days", 30))
    row = DataRequest(
        reference=f"DSR/{date.today().year}/{secrets.token_hex(3).upper()}",
        kind=payload.kind,
        subject_student_id=payload.subject_student_id,
        subject_staff_id=payload.subject_staff_id,
        subject_name=payload.subject_name,
        requested_on=date.today(),
        due_on=date.today() + timedelta(days=statutory_days),
        description=payload.description,
        status="received",
        created_by_id=ctx.principal.id,
    )
    ctx.db.add(row)
    ctx.db.flush()
    emit(
        "data_request:create",
        AuditCategory.CONFIGURATION,
        resource_type="report",
        resource_id=row.id,
        resource_label=row.reference,
        summary=f"{payload.kind} request logged, due {row.due_on:%d %b %Y}",
        severity="notice",
    )
    return {"reference": row.reference, "due_on": row.due_on.isoformat()}
