"""Index specs: idempotent, pymongo default names, and identical to what the plugin and signup API create."""

from __future__ import annotations

import importlib
import sys
from types import ModuleType
from typing import Any

from conftest import PLUGIN_DIR, SIGNUP_API_DIR, load_module

from manceps_core.indexes import (
    FIRM_INDEXES,
    PLATFORM_INDEXES,
    IndexSpec,
    ensure_firm_indexes,
    ensure_platform_indexes,
)
from manceps_core.mongo import MongoClientT, MongoDb

PLUGIN_PACKAGE = "hf_probe_plugin"
PHASE1_FIRM = {
    "carriers", "drivers", "trucks", "brokers", "broker_checks", "contacts", "facilities", "notes", "consent_events",
    "loads", "load_events", "approvals", "imports", "import_rows", "exports", "events", "audit",
}
PHASE1_PLATFORM = {
    "signups", "signup_attempts", "users", "memberships", "invitations", "sessions", "magic_links", "scoped_links",
    "firms", "idempotency_keys", "rate_limits",
}


def _plugin_store() -> ModuleType:
    """Import the plugin's store.py through a synthetic package so its __init__ (and Hermes deps) never run.

    Returns:
        The plugin store module.
    """
    if PLUGIN_PACKAGE not in sys.modules:
        package = ModuleType(PLUGIN_PACKAGE)
        package.__path__ = [str(PLUGIN_DIR)]
        sys.modules[PLUGIN_PACKAGE] = package
    return importlib.import_module(f"{PLUGIN_PACKAGE}.store")


def _indexes(db: MongoDb) -> dict[str, Any]:
    """Read every collection's index information.

    Args:
        db: Database.

    Returns:
        Collection name to index name to index info.
    """
    return {name: db[name].index_information() for name in db.list_collection_names()}


def test_indexes_idempotent(mongo_client: MongoClientT) -> None:
    """Running ensure twice changes nothing and raises nothing."""
    firm = mongo_client["firm_apex_freight"]
    platform = mongo_client["platform"]
    ensure_firm_indexes(firm)
    ensure_platform_indexes(platform)
    first = (_indexes(firm), _indexes(platform))
    ensure_firm_indexes(firm)
    ensure_platform_indexes(platform)
    assert (_indexes(firm), _indexes(platform)) == first


def test_specs_cover_phase1_collections() -> None:
    """Every Phase 1 collection with indexes has a spec list."""
    assert PHASE1_FIRM <= set(FIRM_INDEXES)
    assert PHASE1_PLATFORM <= set(PLATFORM_INDEXES)


def test_index_names_are_pymongo_defaults(mongo_client: MongoClientT) -> None:
    """Each spec's name equals the name the driver generates, so plugin re-creation never conflicts."""
    scratch = mongo_client["scratch"]
    for collection, specs in {**FIRM_INDEXES, **PLATFORM_INDEXES}.items():
        for spec in specs:
            generated = scratch[f"{collection}_probe"].create_index(list(spec.keys))
            assert generated == spec.name, (collection, spec)


def test_firm_indexes_match_plugin(mongo_client: MongoClientT) -> None:
    """The plugin's indexes exist under the same names and options; re-running the plugin adds none."""
    plugin_db = mongo_client["firm_plugin"]
    ours = mongo_client["firm_ours"]
    _plugin_store().ensure_indexes(plugin_db)
    ensure_firm_indexes(ours)
    plugin_info = _indexes(plugin_db)
    our_info = _indexes(ours)
    for collection, info in plugin_info.items():
        for name, details in info.items():
            assert our_info[collection][name] == details, (collection, name)
    _plugin_store().ensure_indexes(ours)
    assert _indexes(ours) == our_info


def test_platform_indexes_match_signup_api(mongo_client: MongoClientT) -> None:
    """The signup queue and attempt indexes match the signup API and worker exactly."""
    signup_store = load_module("signup_probe_store", SIGNUP_API_DIR / "signup_api" / "store.py")
    theirs = mongo_client["platform_signup"]
    ours = mongo_client["platform_ours"]
    signup_store.ensure_indexes(theirs)
    ensure_platform_indexes(ours)
    our_info = _indexes(ours)
    for collection, info in _indexes(theirs).items():
        for name, details in info.items():
            assert our_info[collection][name] == details, (collection, name)


def test_ttl_and_unique_options_applied(mongo_client: MongoClientT) -> None:
    """TTL and uniqueness options reach the server."""
    firm = mongo_client["firm_apex_freight"]
    platform = mongo_client["platform"]
    ensure_firm_indexes(firm)
    ensure_platform_indexes(platform)
    events = firm["events"].index_information()
    assert events["seq_1"]["unique"] is True
    assert events["at_1"]["expireAfterSeconds"] == 30 * 24 * 3600
    idem = platform["idempotency_keys"].index_information()
    assert idem["tenant_id_1_key_1_route_1"]["unique"] is True
    assert idem["created_at_1"]["expireAfterSeconds"] == 24 * 3600
    assert platform["rate_limits"].index_information()["at_1"]["expireAfterSeconds"] == 24 * 3600


def test_index_spec_options() -> None:
    """Options only include what is set."""
    spec = IndexSpec((("phone", 1),), unique=True, sparse=True, expire_after_seconds=60)
    assert spec.options() == {"name": "phone_1", "unique": True, "sparse": True, "expireAfterSeconds": 60}
    assert IndexSpec((("a", 1), ("b", -1))).options() == {"name": "a_1_b_-1"}
