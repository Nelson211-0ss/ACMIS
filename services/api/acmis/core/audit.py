"""The audit trail.

Three streams, deliberately separate because they answer different questions
and have different retention:

* **`audit_event`** (tenant database) — what happened to a record. Who changed
  which field of which student's marks, from what value to what value, when,
  from where, under which authorization decision. This is the stream a degree
  appeal, an examinations board query or an external auditor reads. Ten-year
  retention; append-only.
* **`access_log`** (tenant database) — who *looked*. Reads of sensitive records
  are logged too, because "which member of staff opened this student's
  disability disclosure" is a data-protection question that gets asked and
  cannot be answered from a write log.
* **`platform_audit`** (control plane) — tenant lifecycle, plan changes,
  impersonation, credential rotation. Kept away from tenant data so that
  handing a university a dump of its own database does not hand it the
  platform's operational history.

Append-only is enforced in the database, not here: `alembic/tenant/` installs
a rule that rejects UPDATE and DELETE on `audit_event` for the application
role. Application-level discipline is not evidence — a trail the application
can rewrite is worth nothing in a dispute, and the whole point of this module
is to produce something that is worth something.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

import structlog
from sqlalchemy.orm import Session

from acmis.core.config import settings
from acmis.core.context import RequestContext, current_context
from acmis.core.models import utcnow

log = structlog.get_logger(__name__)

REDACTED = "«redacted»"


class AuditCategory(StrEnum):
    """Coarse grouping, so the governance module can filter without knowing
    every action name in the system."""

    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    ADMISSION = "admission"
    ENROLMENT = "enrolment"
    STUDENT_RECORD = "student_record"
    CURRICULUM = "curriculum"
    ASSESSMENT = "assessment"
    AWARD = "award"
    FINANCE = "finance"
    PEOPLE = "people"
    CONFIGURATION = "configuration"
    INTEGRATION = "integration"
    DATA_EXPORT = "data_export"
    #: Circulation, fines and cataloguing. Its own category because a
    #: library's most sensitive record — who borrowed what — is exactly what
    #: an access review needs to be able to filter *out* of a general trawl.
    LIBRARY = "library"
    #: Attendance, evaluations, observations and audits.
    QUALITY = "quality"
    TENANCY = "tenancy"


class AuditOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"


@dataclass(slots=True)
class FieldChange:
    """One field's before and after.

    Both sides are kept. "Changed the mark" is not an answer in an appeal;
    "changed CSC1101 from 38 to 52 on 4 March at 23:41 from an off-campus
    address" is.
    """

    field: str
    old: Any
    new: Any

    def as_dict(self) -> dict[str, Any]:
        return {"field": self.field, "old": self.old, "new": self.new}


@dataclass(slots=True)
class AuditRecord:
    action: str
    category: AuditCategory
    resource_type: str
    resource_id: str | None = None
    #: Human-readable identity of the record, captured at the time. Denormalised
    #: on purpose: a student number that later changes, or a course that is
    #: retired, must still read correctly in a five-year-old audit line.
    resource_label: str | None = None
    outcome: AuditOutcome = AuditOutcome.SUCCESS
    summary: str = ""
    changes: list[FieldChange] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    #: The authorization decision that allowed (or refused) this action.
    decision_policy_id: str | None = None
    decision_rule_id: str | None = None
    policy_bundle_version: str | None = None
    #: Set when one action is part of a larger operation — a bulk mark upload,
    #: a semester roll-over — so the trail can be read as one event.
    correlation_id: uuid.UUID | None = None
    occurred_at: datetime = field(default_factory=utcnow)
    severity: str = "info"


def redact(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """Strip secrets and special-category data before anything is persisted.

    Applied to audit metadata and to request bodies captured on failure. The
    audit trail is read by more people than the records it describes — a
    governance officer reviewing access does not need an applicant's national
    ID number to do it, and a trail that contains one has widened the blast
    radius of its own disclosure.
    """
    if not payload:
        return {}
    out: dict[str, Any] = {}
    for key, value in payload.items():
        lowered = str(key).lower()
        if any(marker in lowered for marker in settings.audit_redact_fields):
            out[key] = REDACTED
        elif isinstance(value, Mapping):
            out[key] = redact(value)
        elif isinstance(value, (list, tuple)):
            out[key] = [redact(v) if isinstance(v, Mapping) else v for v in value]
        else:
            out[key] = value
    return out


def diff(
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
    *,
    ignore: Iterable[str] = ("updated_at", "version", "updated_by_id"),
) -> list[FieldChange]:
    """Field-level changes between two snapshots.

    `updated_at` and `version` are excluded: they change on every write and
    logging them buries the one field that actually changed under two that
    always do.
    """
    before, after = before or {}, after or {}
    skip = set(ignore)
    changes: list[FieldChange] = []
    for key in sorted(set(before) | set(after)):
        if key in skip:
            continue
        old, new = before.get(key), after.get(key)
        if old != new:
            changes.append(FieldChange(key, _plain(old), _plain(new)))
    return changes


def _plain(value: Any) -> Any:
    """Coerce to something JSONB will accept without a custom encoder."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (uuid.UUID, datetime)):
        return str(value)
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_plain(v) for v in value]
    return str(value)


class AuditWriter:
    """Buffers records and flushes them in the request's own transaction.

    Same transaction as the change it describes, on purpose. A separate
    connection or a fire-and-forget queue means the two can disagree: the mark
    is committed and the audit line is lost to a crash, or the audit line
    survives a rolled-back change and describes something that never happened.
    Both are unusable in a dispute. The cost is that an audit-write failure
    fails the request — which is the correct trade for this data.

    Denials are the exception. A denied request has nothing to commit, so its
    record is written on its own short transaction; otherwise the rollback that
    accompanies a 403 would take the evidence of the 403 with it, and a
    sustained probing attack would leave no trace at all.
    """

    def __init__(self, session: Session, context: RequestContext) -> None:
        self._session = session
        self._context = context
        self._buffer: list[AuditRecord] = []

    def record(self, record: AuditRecord) -> None:
        self._buffer.append(record)

    def record_many(self, records: Sequence[AuditRecord]) -> None:
        self._buffer.extend(records)

    @property
    def pending(self) -> int:
        return len(self._buffer)

    def flush(self) -> None:
        if not self._buffer or not settings.audit_enabled:
            self._buffer.clear()
            return

        from acmis.modules.governance.models import AuditEvent  # local: avoids a cycle

        ctx = self._context
        rows = [
            AuditEvent(
                occurred_at=r.occurred_at,
                request_id=ctx.request_id,
                correlation_id=r.correlation_id,
                actor_id=ctx.principal.id,
                actor_kind=ctx.principal.kind,
                actor_label=ctx.principal.display_name,
                actor_roles=sorted(ctx.principal.roles),
                impersonator_id=ctx.principal.impersonator_id,
                session_id=ctx.principal.session_id,
                module=ctx.module,
                action=r.action,
                category=str(r.category),
                outcome=str(r.outcome),
                severity=r.severity,
                resource_type=r.resource_type,
                resource_id=r.resource_id,
                resource_label=r.resource_label,
                summary=r.summary,
                changes=[c.as_dict() for c in r.changes],
                event_metadata=redact(r.metadata),
                decision_policy_id=r.decision_policy_id,
                decision_rule_id=r.decision_rule_id,
                policy_bundle_version=r.policy_bundle_version,
                ip_address=ctx.ip_address,
                user_agent=(ctx.user_agent or "")[:500] or None,
                http_method=ctx.method,
                http_path=ctx.path,
            )
            for r in self._buffer
        ]
        self._session.add_all(rows)
        self._session.flush()
        log.debug("audit_flushed", count=len(rows))
        self._buffer.clear()

    def discard(self) -> None:
        self._buffer.clear()

    def flush_out_of_band(self, *, dsn: str, tenant_key: str) -> int:
        """Write the buffered records on their own transaction.

        For the denial case. A refused request rolls back, and its audit
        record would roll back with it — losing the one event an access review
        most needs, and making a sustained probing attack leave no trace at
        all. So a denial is committed on a fresh connection, independent of
        the request's doomed transaction.

        Deliberately best-effort: if this write fails, the request has already
        failed and turning an audit problem into a different error for the
        user helps nobody. The failure is logged loudly instead.
        """
        if not self._buffer or not settings.audit_enabled:
            self._buffer.clear()
            return 0

        from acmis.core.db import tenant_session_ctx

        pending = list(self._buffer)
        self._buffer.clear()
        try:
            with tenant_session_ctx(key=tenant_key, dsn=dsn) as session:
                writer = AuditWriter(session, self._context)
                writer.record_many(pending)
                writer.flush()
            return len(pending)
        except Exception:
            log.exception("audit_out_of_band_failed", records=len(pending))
            return 0


def emit(
    action: str,
    category: AuditCategory,
    *,
    resource_type: str,
    resource_id: str | uuid.UUID | None = None,
    resource_label: str | None = None,
    outcome: AuditOutcome = AuditOutcome.SUCCESS,
    summary: str = "",
    changes: Sequence[FieldChange] | None = None,
    metadata: Mapping[str, Any] | None = None,
    severity: str = "info",
    correlation_id: uuid.UUID | None = None,
) -> None:
    """Record an audit event on the current request's writer.

    A no-op outside a request context, so calling it from a unit test or a
    script does not require a database. It is never a hard failure to *try* to
    audit, but a request that reaches `flush()` with a pending record and no
    writer is a wiring bug and says so in the log.
    """
    ctx = current_context()
    if ctx is None:
        log.debug("audit_outside_context", action=action)
        return
    writer = _writer_for(ctx)
    if writer is None:
        log.warning("audit_no_writer", action=action, path=ctx.path)
        return
    writer.record(
        AuditRecord(
            action=action,
            category=category,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id else None,
            resource_label=resource_label,
            outcome=outcome,
            summary=summary,
            changes=list(changes or ()),
            metadata=dict(metadata or {}),
            severity=severity,
            correlation_id=correlation_id,
        )
    )


# The writer is attached to the request context by the middleware. Kept in a
# module-level map keyed by request id rather than on the frozen context, so
# `RequestContext` stays immutable and hashable.
_writers: dict[uuid.UUID, AuditWriter] = {}


def attach_writer(ctx: RequestContext, writer: AuditWriter) -> None:
    _writers[ctx.request_id] = writer


def detach_writer(ctx: RequestContext) -> AuditWriter | None:
    return _writers.pop(ctx.request_id, None)


def _writer_for(ctx: RequestContext) -> AuditWriter | None:
    return _writers.get(ctx.request_id)


def current_writer() -> AuditWriter | None:
    ctx = current_context()
    return _writers.get(ctx.request_id) if ctx else None
