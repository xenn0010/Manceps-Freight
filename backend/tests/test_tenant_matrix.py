"""Tenant matrix generated from the OpenAPI schema: every operation must have a tenancy rule, and every operation
that names a firm resource answers 404 to another firm (ids are never confirmed across firms)."""

from __future__ import annotations

import re
from typing import Any

from conftest import FakeClock
from datakit import created
from fastapi import FastAPI
from fastapi.testclient import TestClient
from loadkit import Fleet, move, new_load, propose, seed_fleet

from manceps_core.mongo import MongoClientT

PUBLIC, USER, PORTAL, FIRM, FIRM_ID = "public", "user", "portal", "firm", "firm_id"
ELSEWHERE = "firm_id_tested_elsewhere"
RULES: dict[str, str] = {
    **dict.fromkeys(("health_get", "readiness_get", "auth_otp_start", "auth_otp_verify", "signup_status_get",
                     "auth_magic_link_start", "auth_magic_link_verify", "auth_refresh", "auth_scoped_exchange"),
                    PUBLIC),
    **dict.fromkeys(("me_get", "me_update", "auth_logout", "auth_logout_all", "auth_switch_firm", "sessions_list",
                     "sessions_delete", "firm_provisioning_get", "invitations_accept"), USER),
    "portal_me_get": PORTAL,
    **dict.fromkeys(("firm_get", "firm_update", "integrations_list", "audit_list", "members_list",
                     "invitations_create", "invitations_list", "carriers_list", "carriers_create", "drivers_list",
                     "drivers_create", "trucks_list", "trucks_create", "brokers_list", "brokers_create",
                     "reference_brokers_list", "contacts_list", "contacts_create", "facilities_list",
                     "facilities_create", "notes_list", "notes_create", "tags_list", "imports_template",
                     "imports_create", "imports_list", "exports_create", "loads_list", "loads_create", "loads_board",
                     "approvals_list", "approvals_create", "approvals_stats", "board_list", "dashboard_summary",
                     "events_stream", "events_list"), FIRM),
    # test_members.py (invitations, members) and test_import_access.py (imports, exports) run these with firm B.
    **dict.fromkeys(("invitations_delete", "members_update", "members_delete", "imports_get", "imports_map",
                     "imports_preview", "imports_report", "imports_commit", "imports_undo", "exports_get",
                     "exports_download"), ELSEWHERE),
    **dict.fromkeys(("carriers_get", "carriers_update", "carriers_delete", "carrier_consent_grant",
                     "carrier_consent_revoke", "carrier_links_create", "carrier_links_delete", "drivers_get",
                     "drivers_update", "drivers_delete", "trucks_get", "trucks_update", "trucks_delete", "brokers_get",
                     "brokers_update", "broker_notes_create", "broker_checks_create", "broker_checks_list",
                     "contacts_get", "contacts_update", "contacts_delete", "facilities_get", "facilities_update",
                     "facilities_delete", "loads_get", "loads_update", "loads_transition", "loads_evaluate",
                     "load_stops_create", "load_stops_update", "load_stops_delete", "load_events_list",
                     "approvals_get", "approvals_decide"), FIRM_ID),
}
BODIES: dict[str, dict[str, Any]] = {
    "carriers_update": {"name": "x"}, "carrier_consent_grant": {"channel": "sms", "method": "verbal"},
    "carrier_links_create": {}, "drivers_update": {"name": "x"}, "trucks_update": {"unit": "x"},
    "brokers_update": {"company": "x"}, "broker_notes_create": {"text": "x"}, "broker_checks_create": {},
    "contacts_update": {"name": "x"}, "facilities_update": {"name": "x"}, "loads_update": {"notes": "x"},
    "loads_transition": {"to": "evaluating"}, "loads_evaluate": {}, "load_stops_create": {"type": "pickup"},
    "load_stops_update": {"city": "x"}, "approvals_decide": {"decision": "approve", "payload_hash": "x"},
}
PARAM = re.compile(r"\{([a-z_]+)\}")


def _operations(app: FastAPI) -> dict[str, tuple[str, str]]:
    spec = app.openapi()
    return {op["operationId"]: (method.upper(), path) for path, ops in spec["paths"].items()
            for method, op in ops.items()}


def _seed(client: TestClient, fleet: Fleet) -> dict[str, str]:
    headers = fleet.firms.headers("dispatcher")
    load = new_load(client, fleet)
    move(client, fleet, load["id"], "evaluating")
    approval = propose(client, fleet, "accept_rate", load["id"], {"rate_cents": 70_000})
    return {
        "carrier_id": fleet.carrier, "driver_id": fleet.driver, "truck_id": fleet.truck,
        "mc": created(client, headers, "/v1/brokers", {"mc_number": "123456"})["mc_number"],
        "contact_id": created(client, headers, "/v1/contacts", {"kind": "other", "name": "C"})["id"],
        "facility_id": created(client, headers, "/v1/facilities", {"name": "F"})["id"],
        "link_id": created(client, headers, f"/v1/carriers/{fleet.carrier}/links", {})["id"],
        "channel": "sms", "load_id": load["id"], "stop_id": load["stops"][0]["id"], "approval_id": approval["id"],
    }


def test_every_route_has_tenant_matrix_entry(app: FastAPI) -> None:
    operations = set(_operations(app))
    assert operations - set(RULES) == set(), "add a tenancy rule for every new route"
    assert set(RULES) - operations == set(), "remove rules for routes that no longer exist"


def test_wrong_tenant_gets_404_on_every_firm_resource(client: TestClient, mongo_client: MongoClientT,
                                                      clock: FakeClock, app: FastAPI) -> None:
    fleet = seed_fleet(client, mongo_client, clock)
    ids = _seed(client, fleet)
    for operation, (method, path) in sorted(_operations(app).items()):
        if RULES[operation] != FIRM_ID:
            continue
        url = PARAM.sub(lambda match: ids[match.group(1)], path)
        response = client.request(method, url, json=BODIES.get(operation), headers=fleet.firms.headers("owner_b"))
        assert response.status_code == 404, (operation, response.status_code, response.text)
    load = client.get(f"/v1/loads/{ids['load_id']}", headers=fleet.firms.headers("viewer")).json()
    assert load["notes"] is None and load["status"] == "evaluating"
    approval = client.get(f"/v1/approvals/{ids['approval_id']}", headers=fleet.firms.headers("viewer")).json()
    assert approval["status"] == "pending"
