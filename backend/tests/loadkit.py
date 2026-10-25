"""Helpers for load, approval, board and event tests: a firm with a carrier, driver and truck, and load builders."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from conftest import START, FakeClock
from datakit import CARRIER, Firms, created, seed_firms
from fastapi.testclient import TestClient

from manceps_core.mongo import MongoClientT

PICKUP_AT = START + timedelta(days=1)
DELIVERY_AT = START + timedelta(days=1, hours=8)


@dataclass(frozen=True)
class Fleet:
    """Firm A's tokens and one carrier, driver and truck."""

    firms: Firms
    carrier: str
    driver: str
    truck: str


def stops(origin: tuple[str, str] = ("Fresno", "CA"), destination: tuple[str, str] = ("Stockton", "CA")) -> list[
        dict[str, Any]]:
    """Build a pickup and a delivery stop.

    Args:
        origin: (city, state).
        destination: (city, state).

    Returns:
        Stop inputs.
    """
    return [
        {"type": "pickup", "city": origin[0], "state": origin[1], "window_start": PICKUP_AT.isoformat(),
         "window_end": (PICKUP_AT + timedelta(hours=1)).isoformat()},
        {"type": "delivery", "city": destination[0], "state": destination[1],
         "window_start": DELIVERY_AT.isoformat(), "window_end": (DELIVERY_AT + timedelta(hours=1)).isoformat()},
    ]


def seed_fleet(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> Fleet:
    """Seed two firms, then an active carrier with a driver and a truck in firm A.

    Args:
        client: Test client.
        mongo_client: Database client.
        clock: Fake clock.

    Returns:
        The fleet.
    """
    firms = seed_firms(client, mongo_client, clock)
    headers = firms.headers("owner")
    carrier = created(client, headers, "/v1/carriers", {**CARRIER, "status": "active", "dispatch_fee_pct": 10.0,
                                                       "rate_floor_per_mile": 2.5})["id"]
    driver = created(client, headers, "/v1/drivers", {"carrier_id": carrier, "name": "Ben Ortiz",
                                                      "phone": "(559) 555-0177"})["id"]
    truck = created(client, headers, "/v1/trucks", {"carrier_id": carrier, "unit": "102", "equipment": "reefer",
                                                    "driver_id": driver})["id"]
    return Fleet(firms, carrier, driver, truck)


def new_load(client: TestClient, fleet: Fleet, **extra: Any) -> dict[str, Any]:
    """Create a load on the fleet's truck as the dispatcher.

    Args:
        client: Test client.
        fleet: Seeded fleet.
        **extra: Field overrides.

    Returns:
        The load.
    """
    body: dict[str, Any] = {"carrier_id": fleet.carrier, "driver_id": fleet.driver, "truck_id": fleet.truck,
                            "broker_mc": "MC-123456", "broker_name": "Valley Logistics", "broker_ref": "VL-30981",
                            "stops": stops(), "loaded_miles": 125, "rate_cents": 65_000, "equipment": "reefer",
                            "commodity": "Produce", "weight_lbs": 36_200, **extra}
    return created(client, fleet.firms.headers("dispatcher"), "/v1/loads", body)


def move(client: TestClient, fleet: Fleet, load_id: str, to: str, role: str = "dispatcher") -> Any:
    """Request a direct status move.

    Args:
        client: Test client.
        fleet: Seeded fleet.
        load_id: Load id.
        to: Target status.
        role: Caller role.

    Returns:
        The response.
    """
    return client.post(f"/v1/loads/{load_id}/transition", json={"to": to}, headers=fleet.firms.headers(role))


def propose(client: TestClient, fleet: Fleet, kind: str, subject_id: str, payload: dict[str, Any],
            subject_type: str = "load") -> dict[str, Any]:
    """Create an approval as the dispatcher.

    Args:
        client: Test client.
        fleet: Seeded fleet.
        kind: Approval kind.
        subject_id: Subject id.
        payload: Payload.
        subject_type: load or carrier.

    Returns:
        The approval.
    """
    body = {"kind": kind, "subject_ref": {"type": subject_type, "id": subject_id}, "payload": payload}
    return created(client, fleet.firms.headers("dispatcher"), "/v1/approvals", body)


def decide(client: TestClient, fleet: Fleet, approval: dict[str, Any], decision: str = "approve",
           role: str = "owner", payload_hash: str | None = None) -> Any:
    """Decide an approval.

    Args:
        client: Test client.
        fleet: Seeded fleet.
        approval: The approval.
        decision: approve or deny.
        role: Caller role.
        payload_hash: Hash to send (the approval's own by default).

    Returns:
        The response.
    """
    body = {"decision": decision, "payload_hash": payload_hash or approval["payload_hash"]}
    return client.post(f"/v1/approvals/{approval['id']}/decision", json=body, headers=fleet.firms.headers(role))


def book(client: TestClient, fleet: Fleet, load: dict[str, Any], rate_cents: int = 65_000) -> dict[str, Any]:
    """Take a load from offered to booked through evaluate and an approved accept_rate.

    Args:
        client: Test client.
        fleet: Seeded fleet.
        load: The load.
        rate_cents: Accepted rate.

    Returns:
        The decided approval.
    """
    assert move(client, fleet, load["id"], "evaluating").status_code == 200
    approval = propose(client, fleet, "accept_rate", load["id"], {"rate_cents": rate_cents})
    response = decide(client, fleet, approval)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "applied", response.text
    return response.json()
