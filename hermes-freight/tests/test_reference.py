"""FMCSA reference data: bond status and broker search fail closed."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest
from hermes_freight import reference, tenant
from pymongo.database import Database


@pytest.fixture
def ref(as_tenant: Callable[..., None]) -> Database:
    as_tenant("apex-freight")
    db = tenant.shared_database(reference.DB_NAME)
    db["sync_meta"].insert_many([{"_id": "broker_bonds", "complete": True, "source_updated": "2026-10-20"},
                                 {"_id": "brokers", "complete": True, "source_updated": "2026-10-20"}])
    return db


def _bond(db: Database, mc: str, cancel: str | None) -> None:
    db["broker_bonds"].insert_one({"_id": f"MC{mc}|{cancel}", "mc_number": mc, "dot_number": "",
                                   "form_name": "BMC-84 surety bond", "surety": "ACME SURETY",
                                   "cancellation_effective_date": cancel})


def test_active_bond_passes(ref: Database) -> None:
    _bond(ref, "123456", None)
    assert reference.bond_status("123456", "")["status"] == "pass"


def test_future_cancellation_still_passes(ref: Database) -> None:
    _bond(ref, "123456", "01/01/2099")
    assert reference.bond_status("123456", "")["status"] == "pass"


def test_past_cancellation_fails(ref: Database) -> None:
    _bond(ref, "123456", "01/01/2020")
    result = reference.bond_status("123456", "")
    assert result["status"] == "fail" and "cancelled" in result["detail"]


def test_unreadable_cancellation_date_is_not_a_pass(ref: Database) -> None:
    _bond(ref, "123456", "garbled")
    assert reference.bond_status("123456", "")["status"] != "pass"


def test_no_bond_on_file_fails(ref: Database) -> None:
    assert reference.bond_status("123456", "")["status"] == "fail"


def test_incomplete_load_is_unknown(ref: Database) -> None:
    ref["sync_meta"].update_one({"_id": "broker_bonds"}, {"$set": {"complete": False}})
    _bond(ref, "123456", None)
    assert reference.bond_status("123456", "")["status"] == "unknown"


def test_no_identifier_is_unknown() -> None:
    assert reference.bond_status("", "")["status"] == "unknown"


def _search(**args: Any) -> dict[str, Any]:
    return json.loads(reference.broker_search(args))


def test_search_by_mc_strips_prefix_and_zeros(ref: Database) -> None:
    ref["brokers"].insert_one({"_id": "777", "dot_number": "777", "mc_numbers": ["123456"],
                               "legal_name": "ACME LOGISTICS", "state": "TX"})
    result = _search(mc_number="MC-0123456")
    assert result["count"] == 1 and result["results"][0]["legal_name"] == "ACME LOGISTICS"
    assert "not consent" in result["note"]


def test_search_rejects_short_name(ref: Database) -> None:
    assert "error" in _search(name="ab")
