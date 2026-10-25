"""Founder rule: booking a load and signing a Rate Con always need a person (the owner); nothing else can do it.

These tests pin the rule so a later autonomy or agent feature cannot quietly turn it off.
"""

from __future__ import annotations

import ast

import pytest
from authkit import firm_db
from bson import ObjectId
from conftest import BACKEND_DIR, TENANT_A, FakeClock, make_principal
from fastapi.testclient import TestClient
from loadkit import book, move, new_load, propose, seed_fleet

from manceps_core.approvals import registry, service
from manceps_core.mongo import MongoClientT
from manceps_core.repo import load_status
from manceps_core.repo.errors import Conflict, Forbidden
from manceps_core.repo.store import WriteContext
from manceps_core.tenancy import PrincipalKind

ALWAYS_HUMAN = ("accept_rate", "approve_ratecon")
PLATFORM_PACKAGES = ("manceps_core", "manceps_api", "manceps_worker")
ALLOWED_CALLERS = frozenset({"manceps_core/approvals/actions.py"})


def test_booking_and_ratecon_kinds_are_always_human_and_owner_only() -> None:
    for name in ALWAYS_HUMAN:
        kind = registry.KINDS[name]
        assert kind.always_human is True
        assert kind.required_role == "owner"
        assert registry.auto_approvable(name, policy_allows=True) is False


def test_only_the_approval_actions_call_move_by_approval() -> None:
    callers: set[str] = set()
    for package in PLATFORM_PACKAGES:
        for path in (BACKEND_DIR / package).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Name | ast.Attribute):
                    name = node.id if isinstance(node, ast.Name) else node.attr
                    if name == "move_by_approval":
                        callers.add(path.relative_to(BACKEND_DIR).as_posix())
    assert callers - {"manceps_core/repo/load_status.py"} == ALLOWED_CALLERS


def _approval(kind: str, decided_by_kind: str, status: str = "approved",
              decision: str = "approve") -> dict[str, object]:
    return {"_id": "a1", "kind": kind, "status": status, "decision": decision,
            "decided_by": {"kind": decided_by_kind, "id": "x", "role": "owner"}}


@pytest.mark.parametrize(("approval", "target"), [
    (_approval("accept_rate", "system"), "booked"),
    (_approval("accept_rate", "scoped"), "approved"),
    (_approval("accept_rate", "agent"), "booked"),
    (_approval("accept_rate", "user", status="pending", decision="approve"), "booked"),
    (_approval("accept_rate", "user", decision="deny", status="denied"), "booked"),
    (_approval("cancel_load", "user"), "booked"),
    (_approval("approve_ratecon", "agent"), "ratecon_received"),
])
def test_status_moves_refuse_anything_but_a_human_approval(approval: dict[str, object], target: str) -> None:
    with pytest.raises(Conflict) as exc:
        load_status.check_human_approval(approval, target)
    assert exc.value.code == "approval_not_valid"


def test_a_human_approval_is_accepted() -> None:
    load_status.check_human_approval(_approval("accept_rate", "user"), "booked")


@pytest.mark.parametrize("kind", ["system", "scoped"])
def test_non_human_principals_cannot_decide(mongo_client: MongoClientT, kind: PrincipalKind) -> None:
    db = firm_db(mongo_client, TENANT_A)
    ctx = WriteContext(who={"kind": kind, "id": "worker"})
    principal = make_principal(role="owner", kind=kind)
    with pytest.raises(Forbidden) as exc:
        service.decide(db, ctx, ObjectId(), principal, "approve", "0" * 64, None)
    assert exc.value.code == "human_required"
    with pytest.raises(Forbidden) as direct:
        service.check_decider(registry.KINDS["accept_rate"], principal)
    assert direct.value.code == "human_required"


def test_every_booked_load_traces_to_a_human_decision(client: TestClient, mongo_client: MongoClientT,
                                                      clock: FakeClock) -> None:
    fleet = seed_fleet(client, mongo_client, clock)
    for _ in range(2):
        load = new_load(client, fleet)
        book(client, fleet, load)
    other = new_load(client, fleet)
    move(client, fleet, other["id"], "evaluating")
    propose(client, fleet, "accept_rate", other["id"], {"rate_cents": 1_000})
    db = firm_db(mongo_client, TENANT_A)
    gated = list(db["load_events"].find({"type": "status_changed", "data.to": {"$in": ["approved", "booked"]}}))
    assert len(gated) == 4
    for entry in gated:
        approval = db["approvals"].find_one({"_id": ObjectId(entry["data"]["approval_id"])})
        assert approval is not None
        assert approval["kind"] == "accept_rate" and approval["decision"] == "approve"
        assert approval["decided_by"]["kind"] == "user" and approval["decided_by"]["role"] == "owner"
    assert db["loads"].count_documents({"status": "booked"}) == 2


def test_platform_code_never_sets_booked_outside_the_machine() -> None:
    offenders: list[str] = []
    for package in PLATFORM_PACKAGES:
        for path in (BACKEND_DIR / package).rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if '"status": "booked"' in text or "'status': 'booked'" in text:
                offenders.append(path.relative_to(BACKEND_DIR).as_posix())
    assert offenders == []
