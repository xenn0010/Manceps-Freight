"""Server-Sent Events: the hub (deterministic ticks), the stream route and the catch-up route."""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Any

import pytest
from authkit import firm_db
from conftest import TENANT_A, TENANT_B, TEST_KEYS_JSON, TEST_KID, FakeClock, make_principal
from fastapi.testclient import TestClient
from loadkit import move, new_load, propose, seed_fleet
from pydantic import SecretStr

from manceps_api.settings import Settings
from manceps_api.sse import EventHub, TooManyStreams
from manceps_core import events
from manceps_core.mongo import MongoClientT
from manceps_core.tenancy import TenantDb

STREAM_SECONDS = 0.8
LIVE_DELAY_SECONDS = 0.2


@pytest.fixture
def settings() -> Settings:
    """Settings with a fast poller and short streams so stream tests finish quickly.

    Returns:
        The settings.
    """
    return Settings(env="test", jwt_active_kid=TEST_KID, jwt_keys_json=SecretStr(TEST_KEYS_JSON),
                    events_poll_seconds=0.05, sse_keepalive_seconds=0.3, sse_max_stream_seconds=STREAM_SECONDS,
                    sse_queue_size=3)


def _hub(mongo_client: MongoClientT, queue_size: int = 10, clock: list[float] | None = None) -> EventHub:
    ticks = clock if clock is not None else [0.0]
    return EventHub(TenantDb(mongo_client), 0.01, 0.0, queue_size, 2, monotonic=lambda: ticks[0])


def _parse(text: str) -> list[dict[str, str]]:
    frames: list[dict[str, str]] = []
    for block in text.split("\n\n"):
        fields: dict[str, str] = {}
        for line in block.splitlines():
            name, _, value = line.partition(": ") if not line.startswith(":") else ("comment", "", line)
            fields[name] = value
        if fields:
            frames.append(fields)
    return frames


def test_sse_two_firms_isolated(mongo_client: MongoClientT) -> None:
    hub = _hub(mongo_client)

    async def scenario() -> tuple[list[int], int]:
        sub_a = await hub.subscribe(make_principal(TENANT_A, user_id="a"), 0)
        sub_b = await hub.subscribe(make_principal(TENANT_B, user_id="b"), 0)
        events.emit(firm_db(mongo_client, TENANT_A), "approval.created", None, {"n": 1})
        await hub.tick(TENANT_A)
        await hub.tick(TENANT_B)
        got = [int(sub_a.queue.get_nowait()["seq"]) for _ in range(sub_a.queue.qsize())]
        size_b = sub_b.queue.qsize()
        await hub.close()
        return got, size_b

    got, size_b = asyncio.run(scenario())
    assert got == [1] and size_b == 0


def test_sse_reset_on_overflow(mongo_client: MongoClientT) -> None:
    hub = _hub(mongo_client, queue_size=2)
    db = firm_db(mongo_client, TENANT_A)

    async def scenario() -> bool:
        sub = await hub.subscribe(make_principal(TENANT_A), 0)
        for number in range(5):
            events.emit(db, "load.status_changed", None, {"n": number})
        await hub.tick(TENANT_A)
        await hub.close()
        return sub.reset

    assert asyncio.run(scenario()) is True


def test_hub_limits_streams_and_stops_idle_pollers(mongo_client: MongoClientT) -> None:
    ticks = [0.0]
    hub = _hub(mongo_client, clock=ticks)

    async def scenario() -> tuple[bool, bool]:
        principal = make_principal(TENANT_A)
        subs = [await hub.subscribe(principal, None) for _ in range(2)]
        with pytest.raises(TooManyStreams):
            await hub.subscribe(principal, None)
        running = hub.running(TENANT_A)
        for sub in subs:
            hub.unsubscribe(sub)
        ticks[0] = 100.0
        await asyncio.sleep(0.05)
        return running, hub.running(TENANT_A)

    running, still = asyncio.run(scenario())
    assert running is True and still is False


def test_stream_replays_and_resumes_with_last_event_id(client: TestClient, mongo_client: MongoClientT,
                                                       clock: FakeClock) -> None:
    fleet = seed_fleet(client, mongo_client, clock)
    load = new_load(client, fleet)
    move(client, fleet, load["id"], "evaluating")
    headers = {**fleet.firms.headers("viewer"), "Last-Event-ID": "0"}
    response = client.get("/v1/events/stream", headers=headers)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    frames = [frame for frame in _parse(response.text) if "event" in frame]
    assert [frame["event"] for frame in frames] == ["load.created", "load.status_changed"]
    assert [frame["id"] for frame in frames] == ["1", "2"]
    resumed = client.get("/v1/events/stream", headers={**fleet.firms.headers("viewer"), "Last-Event-ID": "1"})
    assert [frame["id"] for frame in _parse(resumed.text) if "event" in frame] == ["2"]
    other = client.get("/v1/events/stream", headers={**fleet.firms.headers("owner_b"), "Last-Event-ID": "0"})
    assert [frame for frame in _parse(other.text) if "event" in frame] == []


def test_stream_delivers_live_approval_created(client: TestClient, mongo_client: MongoClientT,
                                               clock: FakeClock) -> None:
    fleet = seed_fleet(client, mongo_client, clock)
    load = new_load(client, fleet)
    move(client, fleet, load["id"], "evaluating")
    created_at: list[float] = []

    def later() -> None:
        time.sleep(LIVE_DELAY_SECONDS)
        propose(client, fleet, "accept_rate", load["id"], {"rate_cents": 70_000})
        created_at.append(time.monotonic())

    worker = threading.Thread(target=later)
    started = time.monotonic()
    worker.start()
    response = client.get(f"/v1/events/stream?access_token={fleet.firms.viewer}")
    worker.join()
    kinds = [frame["event"] for frame in _parse(response.text) if "event" in frame]
    assert "approval.created" in kinds, response.text
    assert created_at and created_at[0] - started < STREAM_SECONDS
    assert ": keepalive" in response.text or kinds


def test_stream_auth_and_bad_last_event_id(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    fleet = seed_fleet(client, mongo_client, clock)
    assert client.get("/v1/events/stream").status_code == 401
    assert client.get("/v1/events/stream?access_token=garbage").status_code == 401
    bad = client.get("/v1/events/stream", headers={**fleet.firms.headers("viewer"), "Last-Event-ID": "x"})
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "invalid_last_event_id"
    idle = client.get("/v1/events/stream", headers=fleet.firms.headers("viewer"))
    assert ": keepalive" in idle.text


def test_stream_overflow_sends_reset(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    fleet = seed_fleet(client, mongo_client, clock)
    for _ in range(5):
        new_load(client, fleet)
    response = client.get("/v1/events/stream", headers={**fleet.firms.headers("viewer"), "Last-Event-ID": "0"})
    frames = _parse(response.text)
    assert frames[-1].get("event") == "reset"


def test_catch_up_route(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    fleet = seed_fleet(client, mongo_client, clock)
    for _ in range(3):
        new_load(client, fleet)
    headers = fleet.firms.headers("viewer")
    page: dict[str, Any] = client.get("/v1/events?after=0&limit=2", headers=headers).json()
    assert [item["seq"] for item in page["items"]] == [1, 2] and page["next_after"] == 2
    rest = client.get("/v1/events?after=2", headers=headers).json()
    assert [item["seq"] for item in rest["items"]] == [3] and rest["next_after"] is None
    assert rest["items"][0]["type"] == "load.created"
    assert client.get("/v1/events?after=-1", headers=headers).status_code == 422
    assert client.get("/v1/events").status_code == 401
    assert client.get("/v1/events?after=0", headers=fleet.firms.headers("owner_b")).json()["items"] == []
