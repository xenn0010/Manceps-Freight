"""Helpers for data-route tests: a firm with every role, a second firm, and small request helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from authkit import (
    PHONE_DISPATCHER_A,
    PHONE_OWNER_A,
    PHONE_OWNER_B,
    PHONE_VIEWER_A,
    bearer,
    member_token,
    owner_token,
)
from conftest import TENANT_A, TENANT_B, FakeClock
from fastapi.testclient import TestClient

from manceps_core.mongo import MongoClientT

CARRIER_PHONE = "+12145550300"
CARRIER_PHONE_2 = "+12145550301"
CARRIER: dict[str, Any] = {
    "phone": "(214) 555-0300", "name": "Lone Wolf", "company": "Lone Wolf Trucking LLC", "mc_number": "MC-0654321",
    "equipment": ["dry_van", "reefer"], "home_base": "Dallas, TX", "tags": ["team_driver"],
    "preferred_lanes": [{"origin": "Dallas, TX", "destination": "Atlanta, GA"}],
}


@dataclass(frozen=True)
class Firms:
    """Access tokens: firm A owner, dispatcher and viewer; firm B owner."""

    owner: str
    dispatcher: str
    viewer: str
    owner_b: str

    def headers(self, role: str) -> dict[str, str]:
        """Return the Authorization header for a role name.

        Args:
            role: owner, dispatcher, viewer or owner_b.

        Returns:
            Header mapping.
        """
        return bearer(str(getattr(self, role)))


def seed_firms(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> Firms:
    """Seed firm A with an owner, dispatcher and viewer, and firm B with an owner.

    Args:
        client: Test client.
        mongo_client: In-memory client.
        clock: Fake clock.

    Returns:
        The tokens.
    """
    return Firms(
        owner=owner_token(client, mongo_client, clock, TENANT_A, PHONE_OWNER_A),
        dispatcher=member_token(client, mongo_client, clock, TENANT_A, PHONE_DISPATCHER_A, "dispatcher"),
        viewer=member_token(client, mongo_client, clock, TENANT_A, PHONE_VIEWER_A, "viewer"),
        owner_b=owner_token(client, mongo_client, clock, TENANT_B, PHONE_OWNER_B),
    )


def created(client: TestClient, headers: dict[str, str], path: str, body: dict[str, Any]) -> dict[str, Any]:
    """POST a create and expect 201.

    Args:
        client: Test client.
        headers: Auth headers.
        path: Collection path.
        body: JSON body.

    Returns:
        The response body.
    """
    response = client.post(path, json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def error_code(response: Any) -> str:
    """Return the envelope error code of a response.

    Args:
        response: httpx response.

    Returns:
        The code.
    """
    return str(response.json()["error"]["code"])
