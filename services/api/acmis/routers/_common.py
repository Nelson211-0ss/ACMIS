"""Helpers shared by the routers."""

from __future__ import annotations

import uuid
from typing import Any

from acmis.core.errors import NotFound


def get_or_404(ctx: Any, model: Any, record_id: uuid.UUID) -> Any:
    """Load a record or 404.

    Loads before authorizing, deliberately: most rules read the record's own
    attributes, so there is nothing to decide until it is in hand. Yes, this
    reveals existence before authorization — acceptable because these ids are
    opaque UUIDs that only ever come from a list the caller was already
    permitted to see. Where that is not true (public verification by serial),
    the endpoint does not take an id at all.
    """
    row = ctx.db.get(model, record_id)
    if row is None or getattr(row, "deleted_at", None) is not None:
        raise NotFound()
    return row
