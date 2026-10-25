"""Per-process fan-out of each firm's `events` log to Server-Sent Events subscribers.

One asyncio poller per firm with subscribers reads `events` where `seq` is past the slowest subscriber's position
every EVENTS_POLL_SECONDS and hands each subscriber the events it has not seen. A subscriber starts at its
`Last-Event-ID` (replaying what it missed) or at the newest event. Each subscriber has a bounded queue; when it is
full the subscriber is marked for reset and its stream ends with `event: reset`, so the client reconnects with
`Last-Event-ID` and catches up from the database. A poller stops SSE_IDLE_STOP_SECONDS after its last subscriber
leaves. The firm database is reached only through a subscriber's principal, never a tenant string. Tests drive
`tick()` by hand.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from manceps_core.events import EVENTS
from manceps_core.mongo import Doc, MongoDb
from manceps_core.tenancy import Principal, TenantDb

BATCH = 500
Monotonic = Callable[[], float]


class TooManyStreams(Exception):
    """The user already holds the maximum number of open streams."""


@dataclass(eq=False)
class Subscription:
    """One open stream."""

    principal: Principal
    last_seq: int
    queue: asyncio.Queue[Doc]
    reset: bool = False

    @property
    def tenant(self) -> str:
        """Return the subscriber's firm.

        Returns:
            Tenant id.
        """
        return str(self.principal.tenant_id)


@dataclass
class EventHub:
    """Fan-out of firm events to subscribers of this process."""

    tenant_db: TenantDb
    poll_seconds: float
    idle_stop_seconds: float
    queue_size: int
    max_per_user: int
    monotonic: Monotonic = field(default=time.monotonic)
    _subs: dict[str, set[Subscription]] = field(default_factory=dict[str, set[Subscription]])
    _pollers: dict[str, asyncio.Task[None]] = field(default_factory=dict[str, asyncio.Task[None]])

    def _db(self, principal: Principal) -> MongoDb:
        """Return a subscriber's firm database.

        Args:
            principal: Subscriber.

        Returns:
            The database.
        """
        return self.tenant_db.for_principal(principal)

    def subscribers(self, tenant: str) -> int:
        """Count a firm's subscribers in this process.

        Args:
            tenant: Tenant id.

        Returns:
            The count.
        """
        return len(self._subs.get(tenant, ()))

    async def subscribe(self, principal: Principal, last_seq: int | None) -> Subscription:
        """Open a subscription and start the firm's poller.

        Args:
            principal: Firm principal.
            last_seq: Last event the client saw, or None to start at the newest.

        Returns:
            The subscription.

        Raises:
            TooManyStreams: When the user already has max_per_user streams.
        """
        mine = [sub for sub in self._subs.get(str(principal.tenant_id), ()) if
                sub.principal.user_id == principal.user_id]
        if len(mine) >= self.max_per_user:
            raise TooManyStreams(principal.user_id)
        if last_seq is None:
            last_seq = await asyncio.to_thread(self._newest, principal)
        sub = Subscription(principal, last_seq, asyncio.Queue[Doc](maxsize=self.queue_size))
        self._subs.setdefault(sub.tenant, set()).add(sub)
        self._ensure_poller(sub.tenant)
        return sub

    def _newest(self, principal: Principal) -> int:
        """Read the firm's newest event sequence.

        Args:
            principal: Firm principal.

        Returns:
            The newest seq, or 0.
        """
        newest = self._db(principal)[EVENTS].find_one({}, {"seq": 1}, sort=[("seq", -1)])
        return int(newest["seq"]) if newest is not None else 0

    def unsubscribe(self, sub: Subscription) -> None:
        """Close a subscription.

        Args:
            sub: The subscription.
        """
        self._subs.get(sub.tenant, set()).discard(sub)

    def _fetch(self, principal: Principal, after: int) -> list[Doc]:
        """Read the next batch of a firm's events.

        Args:
            principal: Any subscriber of the firm.
            after: Lowest position among subscribers.

        Returns:
            Events with seq > after, oldest first.
        """
        cursor = self._db(principal)[EVENTS].find({"seq": {"$gt": after}}, {"_id": 0}, limit=BATCH)
        return list(cursor.sort([("seq", 1)]))

    async def tick(self, tenant: str) -> int:
        """Poll a firm once and deliver new events to its subscribers.

        Args:
            tenant: Tenant id.

        Returns:
            Number of events read.
        """
        subs = list(self._subs.get(tenant, ()))
        if not subs:
            return 0
        found = await asyncio.to_thread(self._fetch, subs[0].principal, min(sub.last_seq for sub in subs))
        for sub in subs:
            self._deliver(sub, found)
        return len(found)

    @staticmethod
    def _deliver(sub: Subscription, found: list[Doc]) -> None:
        """Queue unseen events for one subscriber, marking it for reset on overflow.

        Args:
            sub: Subscriber.
            found: Events, oldest first.
        """
        for event in found:
            if sub.reset or event["seq"] <= sub.last_seq:
                continue
            try:
                sub.queue.put_nowait(event)
            except asyncio.QueueFull:
                sub.reset = True
                return
            sub.last_seq = int(event["seq"])

    def _ensure_poller(self, tenant: str) -> None:
        """Start the firm's poller unless it runs.

        Args:
            tenant: Tenant id.
        """
        task = self._pollers.get(tenant)
        if task is None or task.done():
            self._pollers[tenant] = asyncio.create_task(self._poll(tenant))

    async def _poll(self, tenant: str) -> None:
        """Poll a firm while it has subscribers, stopping idle_stop_seconds after the last leaves.

        Args:
            tenant: Tenant id.
        """
        idle_since: float | None = None
        while True:
            if self.subscribers(tenant):
                idle_since = None
                await self.tick(tenant)
            else:
                idle_since = self.monotonic() if idle_since is None else idle_since
                if self.monotonic() - idle_since >= self.idle_stop_seconds:
                    return
            await asyncio.sleep(self.poll_seconds)

    def running(self, tenant: str) -> bool:
        """Tell whether a firm's poller runs.

        Args:
            tenant: Tenant id.

        Returns:
            True while it runs.
        """
        task = self._pollers.get(tenant)
        return task is not None and not task.done()

    async def close(self) -> None:
        """Stop every poller (app shutdown)."""
        tasks = list(self._pollers.values())
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._pollers.clear()


def stream_record(event: Doc) -> dict[str, Any]:
    """Render an event for the wire and the catch-up route.

    Args:
        event: Stored event.

    Returns:
        {seq, type, ref, data, at}.
    """
    return {"seq": int(event["seq"]), "type": event["type"], "ref": event.get("ref"), "data": event.get("data") or {},
            "at": event["at"]}
