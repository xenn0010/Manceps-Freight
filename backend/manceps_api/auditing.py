"""Write a firm audit record for a request, filling actor, request id and session id from the principal."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import Request

from manceps_core import audit
from manceps_core.tenancy import Principal

from .context import get_context
from .requestinfo import request_id


def record(request: Request, principal: Principal, what: str, ref: Mapping[str, Any] | None,
           before: Mapping[str, Any] | None, after: Mapping[str, Any] | None) -> None:
    """Append an audit record to the principal's firm database.

    Args:
        request: Current request.
        principal: Authenticated caller with an active firm.
        what: Event name, e.g. "firm.update".
        ref: Subject {type, id}.
        before: State before the change, or None.
        after: State after the change, or None.

    Raises:
        TenantError: If the principal has no firm.
    """
    context = get_context(request)
    firm_db = context.tenant_db.for_principal(principal)
    audit.write(firm_db, {"kind": principal.kind, "id": principal.user_id}, what, ref, request_id(request),
                principal.session_id, before, after, context.clock)
