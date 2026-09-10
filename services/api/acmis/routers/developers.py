"""Developer portal endpoints: clients, keys, webhooks, sandbox."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, status
from pydantic import Field
from sqlalchemy import select

from acmis.core.abac import authorize
from acmis.core.audit import AuditCategory, emit
from acmis.core.deps import PageQuery, StaffContext
from acmis.core.errors import Conflict
from acmis.core.models import utcnow
from acmis.core.pagination import keyset_page
from acmis.core.schemas import Page, Reason, Schema
from acmis.modules.developers import service
from acmis.modules.developers.models import (
    ApiClient,
    ApiKey,
    IntegrationLog,
    Webhook,
    WebhookDelivery,
)
from acmis.routers._common import get_or_404

router = APIRouter(prefix="/developers", tags=["developers"])


class ApiClientOut(Schema):
    id: uuid.UUID
    client_id: str
    name: str
    description: str | None
    owner_id: uuid.UUID
    owner_email: str
    support_email: str | None
    environment: str
    client_kind: str
    requested_scopes: list[str]
    granted_scopes: list[str]
    allowed_ip_ranges: list[str]
    rate_limit_per_minute: int
    status: str
    last_used_at: datetime | None
    review_due_on: Any | None


class ApiClientIn(Schema):
    name: Annotated[str, Field(max_length=200)]
    description: str | None = None
    support_email: str | None = None
    environment: Annotated[str, Field(pattern="^(sandbox|live)$")] = "sandbox"
    client_kind: Annotated[str, Field(pattern="^(machine|web|mobile|service_account)$")] = "machine"
    requested_scopes: Annotated[list[str], Field(max_length=60)] = Field(default_factory=list)
    redirect_uris: list[str] = Field(default_factory=list)
    allowed_ip_ranges: list[str] = Field(default_factory=list)


@router.get("/clients", response_model=Page[ApiClientOut])
def list_clients(
    ctx: StaffContext,
    page: PageQuery,
    mine_only: bool = True,
) -> Page[ApiClientOut]:
    authorize(
        engine=ctx.engine,
        action="api_client:list",
        resource_type="api_client",
        resource={"id": None, "owner_id": str(ctx.principal.id), "status": "active"},
        category=AuditCategory.INTEGRATION,
    )
    stmt = select(ApiClient).where(ApiClient.deleted_at.is_(None))
    if mine_only or "developer:admin" not in ctx.principal.permissions:
        stmt = stmt.where(ApiClient.owner_id == ctx.principal.id)
    found = keyset_page(ctx.db, stmt, page=page, key=ApiClient.name, ident=ApiClient.id)
    return Page.of(
        [ApiClientOut.model_validate(r) for r in found.rows],
        limit=page.limit,
        next_cursor=found.next_cursor,
        total=found.total,
    )


@router.post("/clients", response_model=ApiClientOut, status_code=status.HTTP_201_CREATED)
def register_client(payload: ApiClientIn, ctx: StaffContext) -> ApiClientOut:
    """Register an integration. Sandbox is approved on the spot; live is not.

    A sandbox client sees synthetic data, so self-service costs nothing. A live
    client reads real student records, so it arrives `pending` and waits for an
    integration administrator to grant its scopes — and the grant is a subset
    of what was asked for, not a rubber stamp.
    """
    authorize(
        engine=ctx.engine,
        action="api_client:create",
        resource_type="api_client",
        resource={
            "id": None,
            "owner_id": str(ctx.principal.id),
            "status": "pending",
            "environment": payload.environment,
        },
        category=AuditCategory.INTEGRATION,
    )
    client = ApiClient(
        client_id=service.client_id_for(payload.name),
        owner_id=ctx.principal.id,
        owner_email=ctx.principal.email or "",
        status="active" if payload.environment == "sandbox" else "pending",
        # Nothing is granted at registration. A sandbox client gets what it
        # asked for because the data is synthetic; a live one gets nothing
        # until a human decides.
        granted_scopes=(list(payload.requested_scopes) if payload.environment == "sandbox" else []),
        created_by_id=ctx.principal.id,
        **payload.model_dump(),
    )
    ctx.db.add(client)
    ctx.db.flush()
    emit(
        "api_client:create",
        AuditCategory.INTEGRATION,
        resource_type="api_client",
        resource_id=client.id,
        resource_label=f"{client.name} ({client.client_id})",
        summary=f"Registered {payload.environment} client",
        metadata={"requested_scopes": payload.requested_scopes},
        severity="notice",
    )
    return ApiClientOut.model_validate(client)


class GrantScopesIn(Reason):
    granted_scopes: list[str]
    approve: bool = True


@router.post("/clients/{client_id}/scopes", response_model=ApiClientOut)
def grant_scopes(client_id: uuid.UUID, payload: GrantScopesIn, ctx: StaffContext) -> ApiClientOut:
    """Grant a live client its scopes.

    Worth restating what a grant does and does not do: it widens what the
    *token* may attempt, never what it may achieve. The effective authority is
    the intersection with the owner's own permissions, so granting
    `results:approve` to a client owned by a lecturer grants nothing.
    """
    client = get_or_404(ctx, ApiClient, client_id)
    authorize(
        engine=ctx.engine,
        action="api_client:grant",
        resource_type="api_client",
        resource=client,
        category=AuditCategory.INTEGRATION,
    )
    before = list(client.granted_scopes)
    client.granted_scopes = sorted(set(payload.granted_scopes))
    client.status = "active" if payload.approve else "rejected"
    client.approved_by_id = ctx.principal.id
    client.approved_at = utcnow()
    ctx.db.flush()

    emit(
        "api_client:grant",
        AuditCategory.INTEGRATION,
        resource_type="api_client",
        resource_id=client.id,
        resource_label=client.client_id,
        summary=f"Scopes granted: {', '.join(client.granted_scopes) or 'none'}",
        metadata={"before": before, "after": client.granted_scopes, "reason": payload.reason},
        severity="warning",
    )
    return ApiClientOut.model_validate(client)


class ApiKeyOut(Schema):
    id: uuid.UUID
    client_id: uuid.UUID
    name: str
    prefix: str
    environment: str
    scopes: list[str]
    expires_at: datetime | None
    last_used_at: datetime | None
    use_count: int
    revoked_at: datetime | None


class ApiKeyCreatedOut(ApiKeyOut):
    #: Returned exactly once, at creation. Every later read is refused by
    #: `developers.credentials/never-reveal`.
    secret: str
    warning: str = "Copy this key now — it cannot be retrieved again. If it is lost, rotate it."


class ApiKeyIn(Schema):
    name: Annotated[str, Field(max_length=120)]
    scopes: list[str] | None = None
    ttl_days: Annotated[int, Field(ge=1, le=730)] = 365


@router.post(
    "/clients/{client_id}/keys",
    response_model=ApiKeyCreatedOut,
    status_code=status.HTTP_201_CREATED,
)
def create_key(client_id: uuid.UUID, payload: ApiKeyIn, ctx: StaffContext) -> ApiKeyCreatedOut:
    client = get_or_404(ctx, ApiClient, client_id)
    authorize(
        engine=ctx.engine,
        action="api_key:create",
        resource_type="api_key",
        resource={
            "id": None,
            "client_id": str(client.id),
            "owner_id": str(client.owner_id),
            "environment": client.environment,
            "revoked": False,
        },
        category=AuditCategory.INTEGRATION,
    )
    key, plaintext = service.create_api_key(
        ctx.db,
        client=client,
        name=payload.name,
        scopes=payload.scopes,
        ttl_days=payload.ttl_days,
        created_by_id=ctx.principal.id,
    )
    return ApiKeyCreatedOut.model_construct(
        **ApiKeyOut.model_validate(key).model_dump(), secret=plaintext
    )


@router.post("/keys/{key_id}/rotate", response_model=ApiKeyCreatedOut)
def rotate_key(key_id: uuid.UUID, ctx: StaffContext) -> ApiKeyCreatedOut:
    """Issue a replacement key, leaving the old one valid for 24 hours.

    The overlap is the point. Without it, rotating means an outage between
    minting the new key and redeploying the integration — so nobody rotates,
    and credentials live for years.
    """
    key = get_or_404(ctx, ApiKey, key_id)
    authorize(
        engine=ctx.engine,
        action="api_key:rotate",
        resource_type="api_key",
        resource=key,
        category=AuditCategory.INTEGRATION,
    )
    replacement, plaintext = service.rotate_api_key(ctx.db, key=key, actor_id=ctx.principal.id)
    return ApiKeyCreatedOut.model_construct(
        **ApiKeyOut.model_validate(replacement).model_dump(), secret=plaintext
    )


@router.post("/keys/{key_id}/revoke", response_model=ApiKeyOut)
def revoke_key(key_id: uuid.UUID, payload: Reason, ctx: StaffContext) -> ApiKeyOut:
    key = get_or_404(ctx, ApiKey, key_id)
    authorize(
        engine=ctx.engine,
        action="api_key:revoke",
        resource_type="api_key",
        resource=key,
        category=AuditCategory.INTEGRATION,
    )
    if key.revoked_at is not None:
        raise Conflict("This key is already revoked.")
    service.revoke_api_key(ctx.db, key=key, actor_id=ctx.principal.id, reason=payload.reason)
    return ApiKeyOut.model_validate(key)


class WebhookOut(Schema):
    id: uuid.UUID
    client_id: uuid.UUID
    name: str
    url: str
    event_types: list[str]
    is_active: bool
    consecutive_failures: int
    disabled_at: datetime | None
    last_delivery_at: datetime | None
    last_status_code: int | None


class WebhookIn(Schema):
    name: Annotated[str, Field(max_length=160)]
    url: Annotated[str, Field(max_length=500, pattern=r"^https://")]
    event_types: Annotated[list[str], Field(min_length=1, max_length=40)]


class WebhookCreatedOut(WebhookOut):
    signing_secret: str
    signature_scheme: str = (
        "HMAC-SHA256 over '{timestamp}.{body}', sent as 't=<unix>,v1=<hex>' in the "
        "X-ACMIS-Signature header. Reject deliveries older than five minutes."
    )


@router.post(
    "/clients/{client_id}/webhooks",
    response_model=WebhookCreatedOut,
    status_code=status.HTTP_201_CREATED,
)
def create_webhook(
    client_id: uuid.UUID, payload: WebhookIn, ctx: StaffContext
) -> WebhookCreatedOut:
    """Subscribe to platform events.

    HTTPS only — an event payload carries student identifiers, and delivering
    them over plaintext HTTP would undo the rest of the module. The signing
    secret is shown once, like a key.
    """
    from acmis.core.security import hash_secret, token_urlsafe

    client = get_or_404(ctx, ApiClient, client_id)
    authorize(
        engine=ctx.engine,
        action="webhook:create",
        resource_type="webhook",
        resource={
            "id": None,
            "client_id": str(client.id),
            "owner_id": str(client.owner_id),
            "is_active": True,
        },
        category=AuditCategory.INTEGRATION,
    )
    secret = token_urlsafe(32)
    webhook = Webhook(
        client_id=client.id,
        **payload.model_dump(),
        secret_hash=hash_secret(secret),
        created_by_id=ctx.principal.id,
    )
    ctx.db.add(webhook)
    ctx.db.flush()
    emit(
        "webhook:create",
        AuditCategory.INTEGRATION,
        resource_type="webhook",
        resource_id=webhook.id,
        resource_label=webhook.name,
        summary=f"Subscribed to {len(payload.event_types)} event type(s)",
        metadata={"url": payload.url, "events": payload.event_types},
        severity="notice",
    )
    return WebhookCreatedOut.model_construct(
        **WebhookOut.model_validate(webhook).model_dump(), signing_secret=secret
    )


class DeliveryOut(Schema):
    id: uuid.UUID
    webhook_id: uuid.UUID
    event_id: uuid.UUID
    event_type: str
    attempt: int
    attempted_at: datetime
    response_status: int | None
    response_body: str | None
    duration_ms: int | None
    error: str | None
    succeeded: bool
    next_retry_at: datetime | None


@router.get("/webhooks/{webhook_id}/deliveries", response_model=Page[DeliveryOut])
def list_deliveries(
    webhook_id: uuid.UUID,
    ctx: StaffContext,
    page: PageQuery,
    failed_only: bool = False,
) -> Page[DeliveryOut]:
    """Delivery attempts, with the receiver's own response body.

    Kept because "we were never called" versus "you returned a 500" is an
    argument that happens on every integration, and the response body is the
    only thing that settles it.
    """
    webhook = get_or_404(ctx, Webhook, webhook_id)
    authorize(
        engine=ctx.engine,
        action="webhook_delivery:list",
        resource_type="webhook_delivery",
        resource={
            "id": None,
            "webhook_id": str(webhook.id),
            "owner_id": str(webhook.client.owner_id) if webhook.client else None,
            "succeeded": False,
        },
        category=AuditCategory.INTEGRATION,
    )
    stmt = select(WebhookDelivery).where(WebhookDelivery.webhook_id == webhook_id)
    if failed_only:
        stmt = stmt.where(WebhookDelivery.succeeded.is_(False))
    found = keyset_page(
        ctx.db,
        stmt,
        page=page,
        key=WebhookDelivery.attempted_at,
        ident=WebhookDelivery.id,
        descending=True,
    )
    return Page.of(
        [DeliveryOut.model_validate(r) for r in found.rows],
        limit=page.limit,
        next_cursor=found.next_cursor,
        total=found.total,
    )


class IntegrationLogOut(Schema):
    id: uuid.UUID
    occurred_at: datetime
    method: str
    path: str
    status_code: int
    duration_ms: int | None
    denied_reason: str | None
    ip_address: str | None


@router.get("/clients/{client_id}/logs", response_model=Page[IntegrationLogOut])
def list_logs(
    client_id: uuid.UUID,
    ctx: StaffContext,
    page: PageQuery,
    errors_only: bool = False,
) -> Page[IntegrationLogOut]:
    """The developer's own request log.

    Request line, status and timing — never the request body. A developer's
    whole team can read this, and a student's marks do not belong in it.
    `denied_reason` is the one line that turns an opaque 403 into something
    actionable.
    """
    client = get_or_404(ctx, ApiClient, client_id)
    authorize(
        engine=ctx.engine,
        action="integration_log:list",
        resource_type="integration_log",
        resource={
            "id": None,
            "client_id": str(client.id),
            "owner_id": str(client.owner_id),
            "status_code": 200,
        },
        category=AuditCategory.INTEGRATION,
    )
    stmt = select(IntegrationLog).where(IntegrationLog.client_id == client_id)
    if errors_only:
        stmt = stmt.where(IntegrationLog.status_code >= 400)
    found = keyset_page(
        ctx.db,
        stmt,
        page=page,
        key=IntegrationLog.occurred_at,
        ident=IntegrationLog.id,
        descending=True,
    )
    return Page.of(
        [IntegrationLogOut.model_validate(r) for r in found.rows],
        limit=page.limit,
        next_cursor=found.next_cursor,
        total=found.total,
    )


@router.get("/clients/{client_id}/usage", response_model=dict)
def client_usage(client_id: uuid.UUID, ctx: StaffContext, days: int = 7) -> dict[str, Any]:
    client = get_or_404(ctx, ApiClient, client_id)
    authorize(
        engine=ctx.engine,
        action="api_client:read",
        resource_type="api_client",
        resource=client,
        category=AuditCategory.INTEGRATION,
    )
    return service.summarise_usage(ctx.db, client_id=client.id, days=days)


@router.get("/event-types", response_model=list[dict[str, Any]])
def event_catalogue() -> list[dict[str, Any]]:
    """The events a webhook can subscribe to.

    Unauthenticated on purpose: this is documentation, and requiring a token to
    read the list of event names makes the developer portal worse without
    protecting anything.
    """
    return [
        {"type": "applicant.registered", "description": "An applicant created an account."},
        {"type": "application.submitted", "description": "An application was submitted."},
        {"type": "application.decided", "description": "An admission decision was recorded."},
        {"type": "offer.issued", "description": "An admission offer was issued."},
        {"type": "offer.accepted", "description": "An applicant accepted an offer."},
        {"type": "student.enrolled", "description": "An applicant became a student."},
        {"type": "student.status_changed", "description": "A student's standing changed."},
        {
            "type": "registration.approved",
            "description": "A semester course registration was approved.",
        },
        {"type": "invoice.issued", "description": "An invoice was raised."},
        {"type": "payment.settled", "description": "A payment settled against an account."},
        {"type": "payment.unmatched", "description": "Money arrived that could not be matched."},
        {"type": "result.published", "description": "Results were released to students."},
        {"type": "award.conferred", "description": "A qualification was conferred."},
        {"type": "award.revoked", "description": "A qualification was revoked."},
        {"type": "transcript.issued", "description": "An official transcript was issued."},
        {"type": "staff.appointed", "description": "A staff appointment was approved."},
    ]
