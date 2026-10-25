"""Tenant isolation by construction: firm databases come only from a principal; platform rows carry tenant_id."""

from __future__ import annotations

import inspect
from typing import Any, get_type_hints

import pytest
from conftest import PLUGIN_DIR, TENANT_A, TENANT_B, IsolatedMongoClient, load_module, make_principal

from manceps_core.mongo import MongoClientT, MongoDb
from manceps_core.tenancy import TENANT_PATTERN, PlatformRepo, Principal, TenantDb, TenantError

MEMBERSHIPS = "memberships"


def test_tenantdb_has_no_string_tenant_api(mongo_client: MongoClientT) -> None:
    """TenantDb exposes only for_principal, and nothing on it accepts a plain tenant string."""
    public = {name for name, _ in inspect.getmembers(TenantDb) if not name.startswith("_")}
    assert public == {"for_principal"}
    for name in ("__init__", "for_principal"):
        hints = get_type_hints(getattr(TenantDb, name))
        assert str not in hints.values(), name
        assert all("tenant" not in param for param in hints), name
    tenant_db = TenantDb(mongo_client)
    smuggled: Any = TENANT_A
    with pytest.raises(TypeError):
        tenant_db.for_principal(smuggled)


def test_tenantdb_maps_principal_to_firm_database(mongo_client: MongoClientT) -> None:
    """The firm database name is firm_ + id with dashes replaced."""
    db = TenantDb(mongo_client).for_principal(make_principal(TENANT_A))
    prefix = mongo_client.prefix if isinstance(mongo_client, IsolatedMongoClient) else ""
    assert db.name == prefix + "firm_apex_freight"


def test_tenantdb_refuses_principal_without_firm(mongo_client: MongoClientT) -> None:
    """A provisioning principal (no firm yet) gets no database."""
    with pytest.raises(TenantError):
        TenantDb(mongo_client).for_principal(make_principal(None))


@pytest.mark.parametrize("bad", ["", "ab", "Apex", "apex_freight", "-apex", "apex-", "../admin", "a" * 33])
def test_principal_rejects_invalid_tenant(bad: str) -> None:
    """Invalid tenant ids never become principals."""
    with pytest.raises(TenantError):
        make_principal(bad)


def test_principal_is_frozen() -> None:
    """A principal cannot be re-pointed at another firm after authentication."""
    principal = make_principal(TENANT_A)
    with pytest.raises(AttributeError):
        principal.tenant_id = TENANT_B  # pyright: ignore[reportAttributeAccessIssue]


def test_principal_rejects_unknown_role_and_kind() -> None:
    """Role and kind are closed sets."""
    role: Any = "admin"
    kind: Any = "robot"
    with pytest.raises(ValueError, match="role"):
        Principal(user_id="u", tenant_id=TENANT_A, role=role, session_id=None, kind="user")
    with pytest.raises(ValueError, match="kind"):
        Principal(user_id="u", tenant_id=TENANT_A, role="owner", session_id=None, kind=kind)
    with pytest.raises(ValueError, match="user_id"):
        Principal(user_id="", tenant_id=TENANT_A, role="owner", session_id=None, kind="user")


def test_tenant_rule_matches_plugin() -> None:
    """The backend uses exactly the plugin's tenant id rule and database naming."""
    plugin_tenant = load_module("hf_probe_tenant", PLUGIN_DIR / "tenant.py")
    assert plugin_tenant.TENANT_PATTERN.pattern == TENANT_PATTERN.pattern
    assert plugin_tenant.database_name(TENANT_B) == "firm_bolt_logistics"


def test_platform_repo_injects_tenant(platform_db: MongoDb) -> None:
    """Every read, write and delete through PlatformRepo is confined to its tenant."""
    repo_a = PlatformRepo(platform_db, TENANT_A)
    repo_b = PlatformRepo(platform_db, TENANT_B)
    inserted = repo_a.insert_one(MEMBERSHIPS, {"user_id": "u1", "role": "owner", "status": "active"})
    raw = platform_db[MEMBERSHIPS].find_one({"_id": inserted})
    assert raw is not None and raw["tenant_id"] == TENANT_A

    assert repo_b.find_one(MEMBERSHIPS, {"user_id": "u1"}) is None
    assert repo_b.find(MEMBERSHIPS, {}) == []
    assert repo_b.count_documents(MEMBERSHIPS, {}) == 0
    assert repo_b.update_one(MEMBERSHIPS, {"user_id": "u1"}, {"$set": {"role": "viewer"}}) == 0
    assert repo_b.delete_one(MEMBERSHIPS, {"user_id": "u1"}) == 0
    assert repo_b.delete_many(MEMBERSHIPS, {}) == 0

    found = repo_a.find_one(MEMBERSHIPS, {"user_id": "u1"})
    assert found is not None and found["role"] == "owner"
    assert repo_a.update_one(MEMBERSHIPS, {"user_id": "u1"}, {"$set": {"role": "dispatcher"}}) == 1
    assert [doc["role"] for doc in repo_a.find(MEMBERSHIPS, {}, sort=[("user_id", 1)], limit=5)] == ["dispatcher"]
    assert repo_a.count_documents(MEMBERSHIPS, {}) == 1

    repo_b.update_one(MEMBERSHIPS, {"user_id": "u9"}, {"$set": {"role": "viewer"}}, upsert=True)
    upserted = platform_db[MEMBERSHIPS].find_one({"user_id": "u9"})
    assert upserted is not None and upserted["tenant_id"] == TENANT_B
    assert repo_a.delete_many(MEMBERSHIPS, {}) == 1
    assert repo_b.count_documents(MEMBERSHIPS, {}) == 1


def test_platform_repo_rejects_foreign_tenant(platform_db: MongoDb) -> None:
    """Filters, inserts and updates naming another tenant are refused outright."""
    repo = PlatformRepo(platform_db, TENANT_A)
    with pytest.raises(TenantError):
        repo.insert_one(MEMBERSHIPS, {"user_id": "u1", "tenant_id": TENANT_B})
    with pytest.raises(TenantError):
        repo.find_one(MEMBERSHIPS, {"tenant_id": TENANT_B})
    with pytest.raises(TenantError):
        repo.find(MEMBERSHIPS, {"$or": [{"tenant_id": TENANT_B}]})
    with pytest.raises(TenantError):
        repo.update_one(MEMBERSHIPS, {"user_id": "u1"}, {"$set": {"tenant_id": TENANT_B}})
    with pytest.raises(TenantError):
        repo.update_one(MEMBERSHIPS, {"user_id": "u1"}, {"$unset": {"tenant_id": ""}})
    repo.insert_one(MEMBERSHIPS, {"user_id": "u2", "tenant_id": TENANT_A})
    assert repo.count_documents(MEMBERSHIPS, {"tenant_id": TENANT_A}) == 1


def test_platform_repo_rejects_unscoped_collections(platform_db: MongoDb) -> None:
    """Collections without a tenant_id key (e.g. firms, users) are not reachable through PlatformRepo."""
    repo = PlatformRepo(platform_db, TENANT_A)
    with pytest.raises(ValueError, match="firms"):
        repo.find_one("firms", {})
    with pytest.raises(TenantError):
        PlatformRepo(platform_db, "Not A Tenant")


def test_platform_repo_from_principal(platform_db: MongoDb) -> None:
    """A repo can be built from a principal, never for a provisioning one."""
    repo = PlatformRepo.for_principal(platform_db, make_principal(TENANT_B))
    assert repo.tenant_id == TENANT_B
    with pytest.raises(TenantError):
        PlatformRepo.for_principal(platform_db, make_principal(None))
