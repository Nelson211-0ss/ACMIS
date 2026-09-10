"""Structured logging.

Every line is JSON in anything but `local`, and every line carries the request
id, tenant slug and principal id automatically. When a registrar reports that
"the grade did not save at about 11:40", the only workable search is
`tenant=juba AND principal=<id>` across a window — which requires those fields
on lines nobody remembered to add them to.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from acmis.core.config import settings
from acmis.core.context import current_context


def _inject_request_fields(_logger: Any, _name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    ctx = current_context()
    if ctx is not None:
        event_dict.setdefault("request_id", str(ctx.request_id))
        event_dict.setdefault("principal_id", str(ctx.principal.id))
        event_dict.setdefault("principal_kind", ctx.principal.kind)
        if ctx.tenant is not None:
            event_dict.setdefault("tenant", ctx.tenant.slug)
        if ctx.module:
            event_dict.setdefault("module", ctx.module)
    return event_dict


def configure_logging() -> None:
    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        # `add_logger_name` reads `logger.name`, which only a stdlib logger
        # has — it raises against the print factory below. The callsite adder
        # gives the same information from any factory.
        structlog.processors.CallsiteParameterAdder(
            {structlog.processors.CallsiteParameter.MODULE}
        ),
        _inject_request_fields,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    if settings.environment == "local":
        processors.append(structlog.dev.ConsoleRenderer(colors=True))
    else:
        processors.append(structlog.processors.dict_tracebacks)
        processors.append(structlog.processors.JSONRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.DEBUG if settings.debug else logging.INFO
        ),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        level=logging.DEBUG if settings.debug else logging.INFO,
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )
    # SQLAlchemy's own INFO logging duplicates what `sql_echo` already gives us.
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
