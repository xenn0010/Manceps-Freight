"""Idempotency-Key support backed by `platform.idempotency_keys` (24 h).

Same key, route and tenant with the same body replays the stored response with `Idempotency-Replayed: true`; a
different body is 409 `idempotency_conflict`; a request still running under the key is 409 `idempotency_in_progress`.
If the handler fails before saving a response, the key is released so the client can retry.

This module deliberately does not use `from __future__ import annotations`: the dependency closes over the
principal dependency in an `Annotated[...]` signature, which FastAPI must evaluate eagerly.
"""

import json
import re
from collections.abc import AsyncIterator, Callable
from datetime import datetime, timedelta
from typing import Annotated, Any, NoReturn

from fastapi import Depends, Request
from fastapi.encoders import jsonable_encoder
from pymongo.errors import DuplicateKeyError

from manceps_core.hashing import sha256_bytes, sha256_hex
from manceps_core.indexes import IDEMPOTENCY_TTL_SECONDS
from manceps_core.tenancy import PlatformRepo, Principal

from .context import get_context
from .errors import ApiError, ReplayResponse

IDEMPOTENCY_KEYS = "idempotency_keys"
IDEMPOTENCY_HEADER = "Idempotency-Key"
IDEMPOTENCY_TTL = timedelta(seconds=IDEMPOTENCY_TTL_SECONDS)
KEY_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{8,128}$")
IN_PROGRESS = "in_progress"
DONE = "done"
CONFLICT_MESSAGE = "this Idempotency-Key was used with a different request body"
IN_PROGRESS_MESSAGE = "a request with this Idempotency-Key is still being processed"


class IdempotencyGuard:
    """Handle given to a route: call `save` with the response so retries can replay it."""

    def __init__(self, repo: PlatformRepo | None, record_id: Any) -> None:
        """Bind to a claimed key, or to nothing when the request had no key.

        Args:
            repo: Tenant-scoped platform repo, or None without a key.
            record_id: Claimed record id, or None without a key.
        """
        self._repo = repo
        self._record_id = record_id
        self._saved = False

    def save(self, status_code: int, body: Any) -> None:
        """Store the response for replay. A no-op when the request had no key.

        Args:
            status_code: HTTP status the route returns.
            body: JSON-serializable response body.
        """
        if self._repo is None:
            return
        response = {"status_code": status_code, "body": jsonable_encoder(body)}
        self._repo.update_one(IDEMPOTENCY_KEYS, {"_id": self._record_id}, {"$set": {"status": DONE,
                                                                                     "response": response}})
        self._saved = True

    def release(self) -> None:
        """Free the key when no response was saved (the handler failed or chose not to store one)."""
        if self._repo is None or self._saved:
            return
        self._repo.delete_one(IDEMPOTENCY_KEYS, {"_id": self._record_id, "status": IN_PROGRESS})


def _body_hash(raw: bytes) -> str:
    """Hash a request body: canonical JSON when it parses, raw bytes otherwise.

    Args:
        raw: Request body.

    Returns:
        Hex SHA-256 digest.
    """
    try:
        return sha256_hex(json.loads(raw))
    except (ValueError, TypeError):
        return sha256_bytes(raw)


def _resolve(existing: dict[str, Any], body_hash: str) -> NoReturn:
    """Decide what to do with a live record for the same key.

    Args:
        existing: Stored record.
        body_hash: Hash of the current body.

    Raises:
        ApiError: 409 on a different body or while the first request is running.
        ReplayResponse: With the stored response when it is complete.
    """
    if existing.get("body_hash") != body_hash:
        raise ApiError(409, "idempotency_conflict", CONFLICT_MESSAGE)
    if existing.get("status") == DONE:
        stored = existing["response"]
        raise ReplayResponse(int(stored["status_code"]), stored["body"])
    raise ApiError(409, "idempotency_in_progress", IN_PROGRESS_MESSAGE)


def _claim(repo: PlatformRepo, key: str, route: str, body_hash: str, now: datetime) -> Any:
    """Claim a key for this request or resolve an earlier use of it.

    Args:
        repo: Tenant-scoped platform repo.
        key: Idempotency key.
        route: "METHOD /path".
        body_hash: Hash of the body.
        now: Current UTC time.

    Returns:
        The new record id.

    Raises:
        ApiError: 409 conflicts.
        ReplayResponse: When a stored response exists.
    """
    query = {"key": key, "route": route}
    existing = repo.find_one(IDEMPOTENCY_KEYS, query)
    if existing is not None:
        if existing["created_at"] > now - IDEMPOTENCY_TTL:
            _resolve(existing, body_hash)
        repo.delete_one(IDEMPOTENCY_KEYS, {"_id": existing["_id"]})
    record = {**query, "body_hash": body_hash, "status": IN_PROGRESS, "created_at": now}
    try:
        return repo.insert_one(IDEMPOTENCY_KEYS, record)
    except DuplicateKeyError:
        winner = repo.find_one(IDEMPOTENCY_KEYS, query)
        if winner is None:
            raise ApiError(409, "idempotency_in_progress", IN_PROGRESS_MESSAGE) from None
        _resolve(winner, body_hash)


def idempotency_dependency(
    principal_dependency: Callable[..., Principal], *, required: bool = False,
) -> Callable[..., AsyncIterator[IdempotencyGuard]]:
    """Build a FastAPI dependency enforcing Idempotency-Key for one principal source.

    Args:
        principal_dependency: Dependency that returns the authenticated principal.
        required: Reject requests without the header (payment-like routes).

    Returns:
        The dependency, yielding an IdempotencyGuard.
    """

    async def dependency(
        request: Request, principal: Annotated[Principal, Depends(principal_dependency)],
    ) -> AsyncIterator[IdempotencyGuard]:
        key = request.headers.get(IDEMPOTENCY_HEADER)
        if key is None:
            if required:
                raise ApiError(400, "idempotency_key_required", f"the {IDEMPOTENCY_HEADER} header is required")
            yield IdempotencyGuard(None, None)
            return
        if not KEY_PATTERN.fullmatch(key):
            raise ApiError(400, "invalid_idempotency_key", "Idempotency-Key must be 8-128 chars of [A-Za-z0-9_.:-]")
        context = get_context(request)
        repo = PlatformRepo.for_principal(context.platform_db, principal)
        route = f"{request.method} {request.url.path}"
        guard = IdempotencyGuard(repo, _claim(repo, key, route, _body_hash(await request.body()), context.clock()))
        try:
            yield guard
        finally:
            guard.release()

    return dependency
