"""Authorization introspection.

Three endpoints that exist because the alternative is nine frontend apps
reimplementing the policy bundle in TypeScript to decide whether to draw a
button — and getting it subtly wrong, in nine different ways, for as long as
the product lives.

* `/authz/capabilities` — "what may I do with this record?" Asked by every
  detail view. Not audited: asking whether a button should exist is not an
  access to the record.
* `/authz/simulate` — "what would the rules decide for this actor, action and
  resource?" What makes a policy change reviewable before it is enabled.
* `/authz/describe` — the attribute vocabulary, for whoever writes policies.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import Field as PField

from acmis.core.abac import resources
from acmis.core.abac.enforcement import authorize, decide
from acmis.core.audit import AuditCategory
from acmis.core.deps import AuthContext, StaffContext
from acmis.core.errors import ValidationFailed
from acmis.core.schemas import Capability, Schema

router = APIRouter(prefix="/authz", tags=["authz"])


class CapabilityQuery(Schema):
    resource_type: str
    resource_id: uuid.UUID | None = None
    actions: Annotated[list[str], PField(min_length=1, max_length=40)]
    #: Attributes the caller already has in hand, so the server need not reload
    #: the record. Only ever *narrows* a decision: the engine denies by
    #: default, so a caller supplying flattering attributes to a record it has
    #: not been granted still fails the rules that read the real ones — and
    #: the real fetch happens for anything with an id.
    attributes: dict[str, Any] = PField(default_factory=dict)


@router.post("/capabilities", response_model=list[Capability])
def capabilities(payload: CapabilityQuery, ctx: AuthContext) -> list[Capability]:
    if payload.resource_type not in resources.known_types():
        raise ValidationFailed(
            f"'{payload.resource_type}' is not an authorizable resource type.",
            code="unknown_resource_type",
            details={"known": list(resources.known_types())},
        )

    resource: Any = payload.attributes or None
    if payload.resource_id is not None:
        loaded = _load(ctx, payload.resource_type, payload.resource_id)
        if loaded is not None:
            resource = loaded

    results: list[Capability] = []
    for action in payload.actions:
        decision = decide(
            engine=ctx.engine,
            action=action,
            resource_type=payload.resource_type,
            resource=resource,
            resource_id=payload.resource_id,
        )
        results.append(
            Capability(
                action=action,
                allowed=decision.allowed,
                # The reason is safe to return for a *permit*. For a denial it
                # is withheld unless the deployment has opted into
                # explanations — a reason like "you are not the assigned
                # examiner for CSC1101" confirms facts about a record the
                # caller may not read.
                reason=decision.reason if decision.allowed else None,
            )
        )
    return results


def _load(ctx: AuthContext, resource_type: str, resource_id: uuid.UUID) -> Any:
    """Fetch a record for a capability check, if we know its table.

    A deliberately small map. `capabilities` is a UI convenience, and an
    unknown type falls back to the class-level decision — which under
    deny-by-default is the conservative answer.
    """
    from acmis.modules.admissions.models import Application
    from acmis.modules.assessment.models import Award, CourseResult, MarkSheet
    from acmis.modules.curriculum.models import Course, CourseOffering, Programme
    from acmis.modules.finance.models import Invoice, Payment, Waiver
    from acmis.modules.people.models import LeaveRequest, Staff
    from acmis.modules.students.models import Registration, Student

    table = {
        "application": Application,
        "student": Student,
        "registration": Registration,
        "mark_sheet": MarkSheet,
        "course_result": CourseResult,
        "award": Award,
        "programme": Programme,
        "course": Course,
        "course_offering": CourseOffering,
        "invoice": Invoice,
        "payment": Payment,
        "waiver": Waiver,
        "staff": Staff,
        "leave_request": LeaveRequest,
    }.get(resource_type)
    return ctx.db.get(table, resource_id) if table else None


class SimulateIn(Schema):
    action: str
    resource_type: str
    #: Hypothetical subject attributes. Absent keys fall back to the caller's
    #: own, so a small override answers "what would this look like for a dean?"
    subject: dict[str, Any] = PField(default_factory=dict)
    resource: dict[str, Any] = PField(default_factory=dict)
    environment: dict[str, Any] = PField(default_factory=dict)


class RuleTraceOut(Schema):
    policy: str
    rule: str
    effect: str
    matched: bool
    error: str | None = None


class SimulateOut(Schema):
    allowed: bool
    deciding_policy: str | None
    deciding_rule: str | None
    reason: str
    obligations: list[str]
    masked_fields: list[str]
    writable_fields: list[str] | None
    denied_by_default: bool
    bundle_version: str
    trace: list[RuleTraceOut]


@router.post("/simulate", response_model=SimulateOut)
def simulate(payload: SimulateIn, ctx: StaffContext) -> SimulateOut:
    """Dry-run a decision, with the full rule trace.

    Granted broadly — `governance.policy-administration/anyone-may-simulate`
    lets any member of staff use it — because simulating grants nothing. It
    evaluates rules against attributes the caller typed, touches no records,
    and returns no data. Making it hard to reach would only mean policies get
    enabled without being tested, which is how a deny rule locks a university
    out of its own registration window.
    """
    authorize(
        engine=ctx.engine,
        action="policy:simulate",
        resource_type="policy",
        resource={"id": None},
        category=AuditCategory.AUTHORIZATION,
    )

    subject = {**ctx.principal.attributes(), **payload.subject}
    environment = {**ctx.context.environment(), **payload.environment}
    decision = ctx.engine.decide(
        action=payload.action,
        resource_type=payload.resource_type,
        subject=subject,
        resource=payload.resource,
        environment=environment,
        tenant={
            "id": str(ctx.tenant.id),
            "slug": ctx.tenant.slug,
            "features": sorted(ctx.tenant.features),
            **ctx.tenant.settings,
        },
    )
    return SimulateOut(
        allowed=decision.allowed,
        deciding_policy=decision.deciding_policy_id,
        deciding_rule=decision.deciding_rule_id,
        reason=decision.reason,
        obligations=sorted(decision.obligations),
        masked_fields=sorted(decision.masked_fields),
        writable_fields=(
            sorted(decision.writable_fields) if decision.writable_fields is not None else None
        ),
        denied_by_default=not decision.allowed and decision.deciding_policy_id is None,
        bundle_version=ctx.engine.version,
        trace=[
            RuleTraceOut(
                policy=t.policy_id,
                rule=t.rule_id,
                effect=str(t.effect),
                matched=t.matched,
                error=t.error,
            )
            for t in decision.trace
        ],
    )


class ResourceVocabularyOut(Schema):
    resource_type: str
    attributes: list[str]
    protected_fields: list[str]


@router.get("/describe", response_model=list[ResourceVocabularyOut])
def describe_vocabulary(ctx: StaffContext) -> list[ResourceVocabularyOut]:
    """The attributes each resource type publishes to policies.

    This is the reference a policy author needs, and the reason a rule reading
    `resource.departmentIds` fails review rather than silently never matching.
    """
    authorize(
        engine=ctx.engine,
        action="policy:read",
        resource_type="policy",
        resource={"id": None},
    )
    published = resources.published_attributes()
    return [
        ResourceVocabularyOut(
            resource_type=name,
            attributes=sorted(published[name]),
            protected_fields=sorted(resources.protected_fields(name)),
        )
        for name in resources.known_types()
    ]


class BundleOut(Schema):
    version: str
    policy_count: int
    rule_count: int
    lint: list[str]
    policies: list[dict[str, Any]]


@router.get("/bundle", response_model=BundleOut)
def bundle(ctx: StaffContext, include_conditions: bool = Query(False)) -> BundleOut:
    """The loaded bundle, for the governance module's policy browser.

    `include_conditions` is off by default and gated: a condition's text is a
    map of what the institution protects and how, which is useful to an
    administrator and useful to an attacker for the same reason.
    """
    authorize(
        engine=ctx.engine,
        action="policy:read",
        resource_type="policy",
        resource={"id": None},
        audit_reads=True,
    )
    engine = ctx.engine
    show_conditions = include_conditions and "policy:admin" in ctx.principal.permissions
    return BundleOut(
        version=engine.version,
        policy_count=len(engine.policies),
        rule_count=sum(len(p.rules) for p in engine.policies),
        lint=engine.lint(),
        policies=[
            {
                "id": p.id,
                "description": p.description,
                "priority": p.priority,
                "combining": str(p.combining),
                "source": p.source,
                "enabled": p.enabled,
                "overrides": list(p.overrides),
                "target": {
                    "actions": sorted(p.target.actions),
                    "resource_types": sorted(p.target.resource_types),
                    "subject_kinds": sorted(p.target.subject_kinds),
                },
                "rules": [
                    {
                        "id": r.id,
                        "effect": str(r.effect),
                        "description": r.description,
                        "sensitive": r.sensitive,
                        "obligations": list(r.obligations),
                        "mask_fields": list(r.mask_fields),
                        **(
                            {"condition": r.condition.source if r.condition else None}
                            if show_conditions
                            else {}
                        ),
                    }
                    for r in p.rules
                ],
            }
            for p in engine.policies
        ],
    )
