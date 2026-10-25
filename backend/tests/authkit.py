"""Helpers for auth tests: seed firms and members through the real code paths, log in, build headers."""

from __future__ import annotations

from typing import Any

from conftest import GOOD_CODE, FakeClock
from fastapi.testclient import TestClient

from manceps_core import accounts
from manceps_core.mongo import Doc, MongoClientT, MongoDb
from manceps_core.tenancy import PlatformRepo, Principal, Role, TenantDb
from manceps_worker.firm_activate import firm_activate

NATIVE = {"X-Client": "native"}
PHONE_OWNER_A = "+12145550101"
PHONE_OWNER_B = "+12145550202"
PHONE_DISPATCHER_A = "+12145550103"
PHONE_VIEWER_A = "+12145550104"
PHONE_NEW = "+12145550199"


def one(db: MongoDb, collection: str, query: Doc) -> Doc:
    """Fetch exactly the document a test expects to exist.

    Args:
        db: Database.
        collection: Collection name.
        query: Filter.

    Returns:
        The document.
    """
    doc = db[collection].find_one(query)
    assert doc is not None, (collection, query)
    return doc


def bearer(token: str) -> dict[str, str]:
    """Build an Authorization header.

    Args:
        token: Access token.

    Returns:
        Header mapping.
    """
    return {"Authorization": f"Bearer {token}"}


def platform(mongo_client: MongoClientT) -> MongoDb:
    """Return the platform database.

    Args:
        mongo_client: In-memory client.

    Returns:
        The platform database.
    """
    return mongo_client["platform"]


def firm_db(mongo_client: MongoClientT, tenant_id: str) -> MongoDb:
    """Return a firm database through the sanctioned principal API.

    Args:
        mongo_client: In-memory client.
        tenant_id: Firm id.

    Returns:
        The firm database.
    """
    system = Principal(user_id="system:test", tenant_id=tenant_id, role="system", session_id=None, kind="system")
    return TenantDb(mongo_client).for_principal(system)


def seed_firm(mongo_client: MongoClientT, clock: FakeClock, tenant_id: str, phone: str,
              name: str = "Apex Freight") -> str:
    """Create an owner user, a ready signup and run the real activation handler.

    Args:
        mongo_client: In-memory client.
        clock: Fake clock.
        tenant_id: Firm id.
        phone: Owner phone (E.164).
        name: Firm name.

    Returns:
        The owner's user id.
    """
    db = platform(mongo_client)
    user = accounts.create_user(db, clock(), phone=phone)
    signup: Doc = {"_id": f"signup-{tenant_id}", "phone": phone, "firm_name": name, "status": "ready",
                   "tenant_id": tenant_id, "user_id": user["_id"], "attempts": 1, "created_at": clock()}
    db["signups"].insert_one(signup)
    firm_activate(db, TenantDb(mongo_client), signup, clock)
    return str(user["_id"])


def add_member(mongo_client: MongoClientT, clock: FakeClock, tenant_id: str, phone: str, role: Role) -> str:
    """Create a user with a membership in a firm.

    Args:
        mongo_client: In-memory client.
        clock: Fake clock.
        tenant_id: Firm id.
        phone: Member phone.
        role: Membership role.

    Returns:
        The member's user id.
    """
    db = platform(mongo_client)
    user = accounts.create_user(db, clock(), phone=phone)
    repo = PlatformRepo(db, tenant_id)
    repo.insert_one("memberships", {"user_id": user["_id"], "role": role, "status": "active",
                                    "created_at": clock(), "updated_at": clock()})
    return str(user["_id"])


def otp_login(client: TestClient, phone: str, **extra: Any) -> dict[str, Any]:
    """Log in (or sign up) with the fake verifier's good code as a native client.

    Args:
        client: Test client.
        phone: Phone number.
        **extra: Extra body fields (firm_name, accept_terms).

    Returns:
        The token response body.
    """
    response = client.post("/v1/auth/otp/verify", json={"phone": phone, "code": GOOD_CODE, **extra}, headers=NATIVE)
    assert response.status_code == 200, response.text
    return response.json()


def owner_token(client: TestClient, mongo_client: MongoClientT, clock: FakeClock, tenant_id: str,
                phone: str) -> str:
    """Seed a firm and return its owner's access token.

    Args:
        client: Test client.
        mongo_client: In-memory client.
        clock: Fake clock.
        tenant_id: Firm id.
        phone: Owner phone.

    Returns:
        The access token.
    """
    seed_firm(mongo_client, clock, tenant_id, phone, name=tenant_id.replace("-", " ").title())
    return str(otp_login(client, phone)["access_token"])


def member_token(client: TestClient, mongo_client: MongoClientT, clock: FakeClock, tenant_id: str,
                 phone: str, role: Role) -> str:
    """Add a member to an existing firm and return their access token.

    Args:
        client: Test client.
        mongo_client: In-memory client.
        clock: Fake clock.
        tenant_id: Firm id.
        phone: Member phone.
        role: Membership role.

    Returns:
        The access token.
    """
    add_member(mongo_client, clock, tenant_id, phone, role)
    return str(otp_login(client, phone)["access_token"])
