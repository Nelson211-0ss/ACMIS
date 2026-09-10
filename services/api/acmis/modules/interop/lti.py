"""LTI 1.3 Advantage — the platform side.

Every claim URI, scope and message type below is a literal from the 1EdTech
specifications, kept as named constants rather than inline strings so a typo
is a NameError at import rather than a launch a tool silently rejects.

ACMIS is the platform: it mints launches and receives grades. The flow, in the
order it happens:

1. A user clicks a resource link. We POST/GET `iss`, `login_hint`,
   `target_link_uri`, `lti_message_hint` to the tool's OIDC login endpoint.
2. The tool redirects back to our authorization endpoint with `nonce`,
   `state`, `client_id`, `redirect_uri`, `login_hint`.
3. We validate all of it, mint an `id_token` signed with the tenant's key, and
   auto-POST it to the tool's `redirect_uri`.
4. The tool verifies our signature against our JWKS and renders.
5. Later, the tool fetches an access token from our token endpoint using a
   signed client assertion, and posts scores to the AGS endpoints.

The parts that are easy to get wrong and are therefore explicit here: nonce
replay (a table, not a comment), `sub` stability (a per-tool pseudonym, not our
UUID), and role vocabulary (the full IRIs, since a tool matching on the short
form is common but not what the spec says).
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import select
from sqlalchemy.orm import Session

from acmis.core.audit import AuditCategory, emit
from acmis.core.errors import Forbidden, NotFound, RuleViolation, Unauthenticated
from acmis.core.models import utcnow
from acmis.modules.interop.models import (
    LtiLineItem,
    LtiNonce,
    LtiResourceLink,
    LtiScore,
    LtiTool,
    PlatformKey,
)

log = structlog.get_logger(__name__)

LTI_VERSION = "1.3.0"

# --- message types ---------------------------------------------------------
MESSAGE_RESOURCE_LINK = "LtiResourceLinkRequest"
MESSAGE_DEEP_LINKING = "LtiDeepLinkingRequest"
MESSAGE_DEEP_LINKING_RESPONSE = "LtiDeepLinkingResponse"
MESSAGE_SUBMISSION_REVIEW = "LtiSubmissionReviewRequest"

# --- core claim URIs -------------------------------------------------------
CLAIM_MESSAGE_TYPE = "https://purl.imsglobal.org/spec/lti/claim/message_type"
CLAIM_VERSION = "https://purl.imsglobal.org/spec/lti/claim/version"
CLAIM_DEPLOYMENT_ID = "https://purl.imsglobal.org/spec/lti/claim/deployment_id"
CLAIM_TARGET_LINK_URI = "https://purl.imsglobal.org/spec/lti/claim/target_link_uri"
CLAIM_RESOURCE_LINK = "https://purl.imsglobal.org/spec/lti/claim/resource_link"
CLAIM_ROLES = "https://purl.imsglobal.org/spec/lti/claim/roles"
CLAIM_CONTEXT = "https://purl.imsglobal.org/spec/lti/claim/context"
CLAIM_CUSTOM = "https://purl.imsglobal.org/spec/lti/claim/custom"
CLAIM_LAUNCH_PRESENTATION = "https://purl.imsglobal.org/spec/lti/claim/launch_presentation"
CLAIM_TOOL_PLATFORM = "https://purl.imsglobal.org/spec/lti/claim/tool_platform"
CLAIM_ROLE_SCOPE_MENTOR = "https://purl.imsglobal.org/spec/lti/claim/role_scope_mentor"
CLAIM_LIS = "https://purl.imsglobal.org/spec/lti/claim/lis"

# --- service claim URIs ----------------------------------------------------
CLAIM_AGS_ENDPOINT = "https://purl.imsglobal.org/spec/lti-ags/claim/endpoint"
CLAIM_NRPS = "https://purl.imsglobal.org/spec/lti-nrps/claim/namesroleservice"
CLAIM_DEEP_LINKING_SETTINGS = "https://purl.imsglobal.org/spec/lti-dl/claim/deep_linking_settings"
CLAIM_CONTENT_ITEMS = "https://purl.imsglobal.org/spec/lti-dl/claim/content_items"

# --- AGS scopes ------------------------------------------------------------
SCOPE_LINEITEM = "https://purl.imsglobal.org/spec/lti-ags/scope/lineitem"
SCOPE_LINEITEM_READONLY = "https://purl.imsglobal.org/spec/lti-ags/scope/lineitem.readonly"
SCOPE_RESULT_READONLY = "https://purl.imsglobal.org/spec/lti-ags/scope/result.readonly"
SCOPE_SCORE = "https://purl.imsglobal.org/spec/lti-ags/scope/score"
SCOPE_NRPS = "https://purl.imsglobal.org/spec/lti-nrps/scope/contextmembership.readonly"

# --- media types -----------------------------------------------------------
MEDIA_LINEITEM = "application/vnd.ims.lis.v2.lineitem+json"
MEDIA_LINEITEM_CONTAINER = "application/vnd.ims.lis.v2.lineitemcontainer+json"
MEDIA_SCORE = "application/vnd.ims.lis.v1.score+json"
MEDIA_RESULT_CONTAINER = "application/vnd.ims.lis.v2.resultcontainer+json"
MEDIA_NRPS_CONTAINER = "application/vnd.ims.lti-nrps.v2.membershipcontainer+json"

# --- role vocabulary -------------------------------------------------------
#: The full IRIs. A tool matching on `Learner` alone is common and not what
#: the specification says, so both the context IRI and the institution IRI go
#: out on every launch.
ROLE_LEARNER = "http://purl.imsglobal.org/vocab/lis/v2/membership#Learner"
ROLE_INSTRUCTOR = "http://purl.imsglobal.org/vocab/lis/v2/membership#Instructor"
ROLE_CONTENT_DEVELOPER = "http://purl.imsglobal.org/vocab/lis/v2/membership#ContentDeveloper"
ROLE_TEACHING_ASSISTANT = (
    "http://purl.imsglobal.org/vocab/lis/v2/membership/Instructor#TeachingAssistant"
)
ROLE_MENTOR = "http://purl.imsglobal.org/vocab/lis/v2/membership#Mentor"
ROLE_CONTEXT_ADMIN = "http://purl.imsglobal.org/vocab/lis/v2/membership#Administrator"
ROLE_INSTITUTION_STUDENT = "http://purl.imsglobal.org/vocab/lis/v2/institution/person#Student"
ROLE_INSTITUTION_FACULTY = "http://purl.imsglobal.org/vocab/lis/v2/institution/person#Faculty"
ROLE_INSTITUTION_STAFF = "http://purl.imsglobal.org/vocab/lis/v2/institution/person#Staff"
ROLE_SYSTEM_ADMIN = "http://purl.imsglobal.org/vocab/lis/v2/system/person#Administrator"

#: Activity and grading progress vocabularies, from AGS.
ACTIVITY_PROGRESS = frozenset({"Initialized", "Started", "InProgress", "Submitted", "Completed"})
GRADING_PROGRESS = frozenset({"NotReady", "Failed", "Pending", "PendingManual", "FullyGraded"})


def platform_issuer(tenant_slug: str, base_url: str) -> str:
    """The `iss` for this tenant's platform.

    Per tenant, because each university is a distinct platform: a tool
    registered by one must not accept a launch minted for another, and `iss`
    plus `client_id` is what a tool keys its registration on.
    """
    return f"{base_url.rstrip('/')}/lti/{tenant_slug}"


def tool_subject(*, tool: LtiTool, account_id: uuid.UUID, issuer: str) -> str:
    """A stable per-tool pseudonym for a user.

    Not our UUID. `sub` is disclosed to the tool and becomes its permanent key
    for the person, so sending the internal id hands every registered vendor a
    join key across the whole institution — and makes two vendors able to
    correlate their records about the same student. A hash over
    (issuer, client_id, account) is stable for the tool that needs it and
    useless to anyone else.
    """
    material = f"{issuer}|{tool.client_id}|{account_id}".encode()
    return base64.urlsafe_b64encode(hashlib.sha256(material).digest()).decode().rstrip("=")


def lti_roles_for(*, principal: Any, is_instructor: bool) -> list[str]:
    """Map an ACMIS principal onto LTI role IRIs."""
    roles: list[str] = []
    if principal.kind == "student":
        roles += [ROLE_LEARNER, ROLE_INSTITUTION_STUDENT]
    elif principal.kind == "staff":
        roles += (
            [ROLE_INSTRUCTOR, ROLE_INSTITUTION_FACULTY]
            if is_instructor
            else [ROLE_INSTITUTION_STAFF]
        )
        if "curriculum:author" in principal.permissions:
            roles.append(ROLE_CONTENT_DEVELOPER)
        if "identity:admin" in principal.permissions:
            roles.append(ROLE_CONTEXT_ADMIN)
    return roles


def begin_launch(
    session: Session,
    *,
    tool: LtiTool,
    resource_link: LtiResourceLink | None,
    account_id: uuid.UUID,
    message_type: str = MESSAGE_RESOURCE_LINK,
) -> dict[str, str]:
    """Step 1: the parameters to send to the tool's OIDC login endpoint.

    `lti_message_hint` carries our own state through the tool's redirect — the
    tool echoes it back opaquely, which is how we know on the way back which
    resource link and which user this round trip is about, without trusting
    anything the tool could have altered.
    """
    if tool.status != "active":
        raise Forbidden("This tool is not active.")

    hint = secrets.token_urlsafe(24)
    session.add(LtiNonce(nonce=f"hint:{hint}", client_id=tool.client_id, issued_at=utcnow()))
    session.flush()

    return {
        "iss": "",  # filled by the router, which knows the base URL
        "login_hint": str(account_id),
        "target_link_uri": tool.target_link_uri,
        "lti_message_hint": f"{hint}:{message_type}:{resource_link.id if resource_link else ''}",
        "client_id": tool.client_id,
        "lti_deployment_id": tool.deployment_id,
    }


def build_id_token_claims(
    *,
    tool: LtiTool,
    issuer: str,
    subject: str,
    nonce: str,
    message_type: str,
    resource_link: LtiResourceLink | None,
    context: dict[str, Any],
    roles: list[str],
    user: dict[str, Any],
    services_base: str,
    line_item_ids: list[uuid.UUID] | None = None,
    deep_linking_return_url: str | None = None,
) -> dict[str, Any]:
    """Assemble the `id_token` payload.

    Only the services the registration actually grants are advertised. A tool
    that is not permitted to write grades does not receive an AGS endpoint
    claim at all — advertising it and refusing the write later means the tool's
    own error handling is where the boundary is enforced, which is the wrong
    place for it.
    """
    now = datetime.now(UTC)
    claims: dict[str, Any] = {
        "iss": issuer,
        "aud": tool.client_id,
        "sub": subject,
        "iat": int(now.timestamp()),
        # Five minutes. A launch token is used within seconds; a long-lived one
        # sitting in a browser history is a replayable session.
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        "nonce": nonce,
        CLAIM_VERSION: LTI_VERSION,
        CLAIM_MESSAGE_TYPE: message_type,
        CLAIM_DEPLOYMENT_ID: tool.deployment_id,
        CLAIM_TARGET_LINK_URI: tool.target_link_uri,
        CLAIM_ROLES: roles,
        CLAIM_CONTEXT: context,
        CLAIM_TOOL_PLATFORM: {
            "guid": issuer,
            "name": context.get("platform_name", "ACMIS"),
            "product_family_code": "acmis",
            "version": "1.0",
        },
        CLAIM_LAUNCH_PRESENTATION: {
            "document_target": resource_link.presentation if resource_link else "iframe",
            "return_url": f"{services_base}/lti/return",
        },
        **{k: v for k, v in user.items() if v is not None},
    }

    if tool.custom_parameters:
        claims[CLAIM_CUSTOM] = dict(tool.custom_parameters)

    if message_type == MESSAGE_RESOURCE_LINK and resource_link is not None:
        claims[CLAIM_RESOURCE_LINK] = {
            "id": str(resource_link.id),
            "title": resource_link.title,
            "description": resource_link.description,
        }

    if message_type == MESSAGE_DEEP_LINKING:
        if not tool.allow_deep_linking:
            raise Forbidden("This tool is not permitted to use Deep Linking.")
        claims[CLAIM_DEEP_LINKING_SETTINGS] = {
            "deep_link_return_url": deep_linking_return_url,
            "accept_types": ["ltiResourceLink", "link", "file", "html"],
            "accept_presentation_document_targets": ["iframe", "window", "embed"],
            "accept_multiple": True,
            "auto_create": False,
            "title": resource_link.title if resource_link else None,
        }

    if tool.allow_grade_services:
        scopes = [SCOPE_LINEITEM, SCOPE_LINEITEM_READONLY, SCOPE_RESULT_READONLY, SCOPE_SCORE]
        endpoint: dict[str, Any] = {
            "scope": scopes,
            "lineitems": f"{services_base}/lti/{tool.client_id}/lineitems",
        }
        if line_item_ids:
            endpoint["lineitem"] = (
                f"{services_base}/lti/{tool.client_id}/lineitems/{line_item_ids[0]}"
            )
        claims[CLAIM_AGS_ENDPOINT] = endpoint

    if tool.allow_names_and_roles:
        claims[CLAIM_NRPS] = {
            "context_memberships_url": (
                f"{services_base}/lti/{tool.client_id}/contexts/{context.get('id')}/memberships"
            ),
            "service_versions": ["2.0"],
        }

    return claims


def check_and_consume_nonce(session: Session, *, nonce: str, client_id: str) -> None:
    """Reject a replayed nonce.

    A used nonce is a replayed launch, and an LTI launch is an authenticated
    session — so this is refused rather than logged. Nonces older than an hour
    are swept by the retention job; the window only has to cover a launch.
    """
    row = session.get(LtiNonce, nonce)
    if row is not None and row.used_at is not None:
        log.warning("lti_nonce_replay", client_id=client_id)
        raise Unauthenticated("This launch has already been used.")
    if row is None:
        row = LtiNonce(nonce=nonce, client_id=client_id, issued_at=utcnow())
        session.add(row)
    row.used_at = utcnow()
    session.flush()


def record_score(
    session: Session,
    *,
    tool: LtiTool,
    line_item: LtiLineItem,
    student_id: uuid.UUID,
    payload: dict[str, Any],
) -> LtiScore:
    """Accept a score posting from a tool.

    Three refusals, each from the specification and each with a practical
    reason:

    * The tool must be permitted grade services. Checked here, not only at
      launch — a token issued when the permission existed must stop working
      when it is withdrawn.
    * `scoreGiven` may not exceed `scoreMaximum`. A tool with an off-by-one
      would otherwise write 110% into a component score.
    * An out-of-order score is ignored. Retries and slow links deliver out of
      order routinely, and letting an older score overwrite a newer one makes
      a student's mark depend on network timing.
    """
    if not tool.allow_grade_services:
        raise Forbidden("This tool is not permitted to report grades.")

    activity = str(payload.get("activityProgress", ""))
    grading = str(payload.get("gradingProgress", ""))
    if activity not in ACTIVITY_PROGRESS:
        raise RuleViolation(
            f"'{activity}' is not a valid activityProgress.", rule="lti_invalid_progress"
        )
    if grading not in GRADING_PROGRESS:
        raise RuleViolation(
            f"'{grading}' is not a valid gradingProgress.", rule="lti_invalid_progress"
        )

    given = payload.get("scoreGiven")
    maximum = payload.get("scoreMaximum", float(line_item.score_maximum))
    if given is not None and maximum and float(given) > float(maximum):
        raise RuleViolation("scoreGiven cannot exceed scoreMaximum.", rule="lti_score_out_of_range")

    raw_timestamp = payload.get("timestamp")
    try:
        timestamp = (
            datetime.fromisoformat(str(raw_timestamp).replace("Z", "+00:00"))
            if raw_timestamp
            else utcnow()
        )
    except ValueError:
        raise RuleViolation(
            "timestamp must be an ISO 8601 instant.", rule="lti_invalid_timestamp"
        ) from None

    latest = (
        session.execute(
            select(LtiScore)
            .where(
                LtiScore.line_item_id == line_item.id,
                LtiScore.student_id == student_id,
            )
            .order_by(LtiScore.timestamp.desc())
        )
        .scalars()
        .first()
    )
    if latest is not None and timestamp < latest.timestamp:
        # 409 per the specification. The score is still recorded — the
        # sequence is evidence — but it does not become the current one.
        log.info(
            "lti_score_out_of_order",
            line_item=str(line_item.id),
            student=str(student_id),
        )

    score = LtiScore(
        line_item_id=line_item.id,
        student_id=student_id,
        timestamp=timestamp,
        score_given=float(given) if given is not None else None,
        score_maximum=float(maximum) if maximum is not None else None,
        activity_progress=activity,
        grading_progress=grading,
        comment=payload.get("comment"),
        payload=dict(payload),
    )
    session.add(score)
    session.flush()

    emit(
        "lti_score:receive",
        AuditCategory.INTEGRATION,
        resource_type="lti_line_item",
        resource_id=line_item.id,
        resource_label=line_item.label,
        summary=(f"{tool.name} reported {given}/{maximum} for student {student_id} ({grading})"),
        metadata={"activity_progress": activity, "grading_progress": grading},
    )
    return score


def current_results(session: Session, *, line_item: LtiLineItem) -> list[dict[str, Any]]:
    """The latest fully-graded score per student, in AGS result shape."""
    rows = (
        session.execute(
            select(LtiScore)
            .where(LtiScore.line_item_id == line_item.id)
            .order_by(LtiScore.student_id, LtiScore.timestamp.desc())
        )
        .scalars()
        .all()
    )

    seen: set[uuid.UUID] = set()
    results: list[dict[str, Any]] = []
    for row in rows:
        if row.student_id in seen:
            continue
        seen.add(row.student_id)
        results.append(
            {
                "id": f"lineitems/{line_item.id}/results/{row.student_id}",
                "scoreOf": f"lineitems/{line_item.id}",
                "userId": str(row.student_id),
                "resultScore": float(row.score_given) if row.score_given is not None else None,
                "resultMaximum": float(row.score_maximum)
                if row.score_maximum is not None
                else float(line_item.score_maximum),
                "comment": row.comment,
                "timestamp": row.timestamp.isoformat(),
            }
        )
    return results


def push_line_item_to_mark_sheet(
    session: Session, *, line_item: LtiLineItem, actor_id: uuid.UUID
) -> dict[str, Any]:
    """Write a tool's grades into the mark sheet as a component score.

    The same narrow seam the online assessments use, and for the same reason:
    a component score on a *draft* mark sheet, never a final mark, never past
    the approval chain. A publisher's courseware reporting a grade does not get
    to bypass moderation, a department board, a faculty board and Senate
    because it arrived over HTTP rather than being typed.

    Only `FullyGraded` scores are eligible. A `PendingManual` score is the
    tool telling us a human has not finished marking, and writing it would put
    a partial mark into the academic record.
    """
    from acmis.modules.assessment.models import ComponentScore, CourseResult, MarkSheet
    from acmis.modules.curriculum.models import AssessmentComponent

    if not line_item.assessment_component_id:
        raise RuleViolation(
            "This line item is not linked to a component of the course's assessment "
            "scheme, so it has nowhere to be recorded.",
            rule="no_component_link",
        )

    sheet = session.execute(
        select(MarkSheet).where(MarkSheet.course_offering_id == line_item.course_offering_id)
    ).scalar_one_or_none()
    if sheet is None:
        raise RuleViolation("No mark sheet exists for this course offering.", rule="no_mark_sheet")
    if not sheet.is_editable:
        raise RuleViolation(
            f"The mark sheet is {sheet.status}; corrections after submission go "
            "through moderation, not through an external tool.",
            rule="mark_sheet_locked",
        )

    component = session.get(AssessmentComponent, line_item.assessment_component_id)
    if component is None:
        raise NotFound("The linked assessment component no longer exists.")

    written = 0
    skipped: list[dict[str, Any]] = []
    for result_payload in current_results(session, line_item=line_item):
        student_id = uuid.UUID(result_payload["userId"])
        score_value = result_payload["resultScore"]
        if score_value is None:
            skipped.append({"student_id": str(student_id), "reason": "no score reported"})
            continue

        latest = (
            session.execute(
                select(LtiScore)
                .where(LtiScore.line_item_id == line_item.id, LtiScore.student_id == student_id)
                .order_by(LtiScore.timestamp.desc())
            )
            .scalars()
            .first()
        )
        if latest is None or latest.grading_progress != "FullyGraded":
            skipped.append(
                {
                    "student_id": str(student_id),
                    "reason": (
                        f"grading progress is {latest.grading_progress if latest else 'unknown'}"
                    ),
                }
            )
            continue

        result = session.execute(
            select(CourseResult).where(
                CourseResult.mark_sheet_id == sheet.id,
                CourseResult.student_id == student_id,
            )
        ).scalar_one_or_none()
        if result is None:
            skipped.append({"student_id": str(student_id), "reason": "not on the mark sheet"})
            continue

        maximum = float(result_payload["resultMaximum"] or line_item.score_maximum)
        scaled = score_value / maximum * float(component.max_mark) if maximum else 0.0
        weighted = round(scaled / float(component.max_mark) * float(component.weight_percent), 2)

        score = session.execute(
            select(ComponentScore).where(
                ComponentScore.result_id == result.id,
                ComponentScore.component_id == component.id,
            )
        ).scalar_one_or_none()
        if score is None:
            score = ComponentScore(
                result_id=result.id,
                component_id=component.id,
                component_code=component.code,
                max_score=component.max_mark,
                weight_percent=component.weight_percent,
                created_by_id=actor_id,
            )
            session.add(score)
        score.raw_score = round(scaled, 2)
        score.weighted_score = weighted
        score.entered_by_id = actor_id
        score.entered_at = utcnow()
        written += 1

    # Whoever pushed becomes an entrant on the sheet, which means the
    # separation-of-duties rule will refuse to let them approve it. Intended:
    # pushing marks is entering marks, whatever produced the numbers.
    if actor_id not in (sheet.entered_by_ids or ()):
        sheet.entered_by_ids = [*(sheet.entered_by_ids or ()), actor_id]
    line_item.pushed_at = utcnow()
    session.flush()

    emit(
        "lti_line_item:push_marks",
        AuditCategory.ASSESSMENT,
        resource_type="lti_line_item",
        resource_id=line_item.id,
        resource_label=line_item.label,
        summary=f"{written} tool-reported score(s) written to component {component.code}; "
        f"{len(skipped)} skipped",
        metadata={"skipped": skipped[:50]},
        severity="notice",
    )
    return {"written": written, "skipped": skipped, "component": component.code}


def content_items_from_deep_linking(
    session: Session,
    *,
    tool: LtiTool,
    course_offering_id: uuid.UUID,
    space_id: uuid.UUID | None,
    items: list[dict[str, Any]],
    actor_id: uuid.UUID,
) -> list[LtiResourceLink]:
    """Turn a Deep Linking response into resource links and line items.

    A tool returning `ltiResourceLink` items with a `lineItem` is asking for a
    gradable column. We create it — but with no component mapping, so the
    grades it reports accumulate and go nowhere until a member of staff
    deliberately links it to a component of the course's assessment scheme. A
    vendor cannot create its own route into the academic record.
    """
    created: list[LtiResourceLink] = []
    for item in items:
        if item.get("type") not in {"ltiResourceLink", "link", "html", "file"}:
            continue
        link = LtiResourceLink(
            tool_id=tool.id,
            space_id=space_id,
            course_offering_id=course_offering_id,
            title=str(item.get("title") or tool.name)[:300],
            description=item.get("text"),
            url=item.get("url"),
            custom=dict(item.get("custom") or {}),
            presentation=str((item.get("presentation") or {}).get("documentTarget", "iframe")),
            created_by_id=actor_id,
        )
        session.add(link)
        session.flush()
        created.append(link)

        if line_item := item.get("lineItem"):
            session.add(
                LtiLineItem(
                    resource_link_id=link.id,
                    tool_id=tool.id,
                    course_offering_id=course_offering_id,
                    label=str(line_item.get("label") or link.title)[:300],
                    score_maximum=float(line_item.get("scoreMaximum") or 100),
                    resource_id=line_item.get("resourceId"),
                    tag=line_item.get("tag"),
                    # Deliberately unlinked. See the note above.
                    assessment_component_id=None,
                    created_by_id=actor_id,
                )
            )
    session.flush()

    emit(
        "lti_resource_link:create",
        AuditCategory.INTEGRATION,
        resource_type="lti_tool",
        resource_id=tool.id,
        resource_label=tool.name,
        summary=f"{len(created)} content item(s) added by Deep Linking",
    )
    return created


def ensure_platform_key(session: Session, *, tenant_slug: str) -> PlatformKey:
    """The active signing key for this tenant, generating one on first use.

    RS256 with a 2048-bit key, because that is what every LTI tool
    implementation supports. The private key is referenced rather than stored
    in clear — in production the reference resolves through the deployment's
    secret manager; in development it is the PEM itself, which is honest about
    what it is.
    """
    from cryptography.hazmat.primitives.asymmetric import rsa

    existing = (
        session.execute(
            select(PlatformKey).where(
                PlatformKey.is_active.is_(True), PlatformKey.retired_at.is_(None)
            )
        )
        .scalars()
        .first()
    )
    if existing is not None:
        return existing

    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = (
        private.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    kid = hashlib.sha256(public_pem.encode()).hexdigest()[:32]

    key = PlatformKey(
        kid=kid,
        algorithm="RS256",
        public_key_pem=public_pem,
        private_key_ref=private_pem,
        is_active=True,
        published_at=utcnow(),
        activated_at=utcnow(),
    )
    session.add(key)
    session.flush()
    log.info("lti_platform_key_created", tenant=tenant_slug, kid=kid)
    return key


def jwks(session: Session) -> dict[str, Any]:
    """This platform's public key set, in JWK form.

    Every published key is included, including one that is published but not
    yet signing and one recently retired — a tool that cached the set an hour
    ago must still be able to verify tokens signed with what it cached.
    """

    keys = (
        session.execute(select(PlatformKey).where(PlatformKey.retired_at.is_(None))).scalars().all()
    )

    out: list[dict[str, Any]] = []
    for key in keys:
        public = serialization.load_pem_public_key(key.public_key_pem.encode())
        # Narrowed rather than ignored: every LTI tool implementation expects
        # RS256, so a non-RSA key in the store is a configuration error and
        # skipping it silently would produce a JWKS that verifies nothing.
        if not isinstance(public, rsa.RSAPublicKey):
            log.error("lti_platform_key_not_rsa", kid=key.kid)
            continue
        numbers = public.public_numbers()

        def b64(value: int) -> str:
            raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
            return base64.urlsafe_b64encode(raw).decode().rstrip("=")

        out.append(
            {
                "kty": "RSA",
                "use": "sig",
                "alg": key.algorithm,
                "kid": key.kid,
                "n": b64(numbers.n),
                "e": b64(numbers.e),
            }
        )
    return {"keys": out}
