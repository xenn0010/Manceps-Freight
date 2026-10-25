"""Imports over HTTP: acceptance criteria 9 to 12, dedupe, merge, product rules, events and audit."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from authkit import firm_db, one
from conftest import TENANT_A, TEST_KEYS_JSON, TEST_KID, FakeClock
from datakit import CARRIER, created, error_code, seed_firms
from fastapi.testclient import TestClient
from importkit import (
    commit,
    committed,
    csv_bytes,
    fixture_bytes,
    fresh_owner,
    run_jobs,
    upload,
    uploaded,
    xlsx_bytes,
)
from pydantic import SecretStr

from manceps_api.app import create_app
from manceps_api.integrations.configured import Integrations
from manceps_api.settings import Settings
from manceps_core.mongo import MongoClientT

CARRIER_HEADER = ("Name", "Phone", "MC#", "Email")
EXISTING = 20
INVALID = 5
TOTAL = 1000
SMALL_MAX_BYTES = 50_000
SMALL_MAX_ROWS = 100


def _phone(index: int) -> str:
    """Make a distinct synthetic US number.

    Args:
        index: Row index.

    Returns:
        Number like (214) 555-1234 written with an area code per thousand.
    """
    return f"(214) {600 + index // 1000:03d}-{index % 10000:04d}"


def _thousand_rows() -> list[list[str]]:
    """1,000 carrier rows: the first EXISTING already exist, the last INVALID have bad phones.

    Returns:
        Rows.
    """
    rows = [[f"Carrier {index}", _phone(index), str(100000 + index), f"c{index}@fleet.example"]
            for index in range(TOTAL)]
    for row in rows[-INVALID:]:
        row[1] = "555-01"
    return rows


def test_carrier_csv_1000_rows_preview_commit_and_reupload(client: TestClient, mongo_client: MongoClientT,
                                                           clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    owner = firms.headers("owner")
    for index in range(EXISTING):
        created(client, owner, "/v1/carriers", {"phone": _phone(index), "name": f"Existing {index}"})
    content = csv_bytes(CARRIER_HEADER, _thousand_rows())
    first = uploaded(client, owner, "carriers", "big.csv", content)
    stats = first["stats"]
    assert first["status"] == "mapped" and first["unmapped_required"] == []
    assert (stats["rows"], stats["valid"], stats["invalid"]) == (TOTAL, TOTAL - INVALID, INVALID)
    assert (stats["new"], stats["existing"], stats["duplicates_in_file"]) == (TOTAL - INVALID - EXISTING, EXISTING, 0)
    preview = client.get(f"/v1/imports/{first['id']}/preview?duplicate_strategy=skip", headers=owner).json()
    assert preview["counts"] == {"create": TOTAL - INVALID - EXISTING, "update": 0, "merge": 0,
                                 "skip": EXISTING + INVALID}
    assert len(preview["rows"]) == 50 and preview["rows"][0]["action"] == "skip"
    assert preview["rows"][0]["reason"] == "exists" and preview["rows"][0]["match_id"]
    done = committed(client, mongo_client, clock, owner, first["id"], "skip")
    assert done["status"] == "committed"
    assert (done["stats"]["created"], done["stats"]["skipped"]) == (TOTAL - INVALID - EXISTING, EXISTING + INVALID)
    db = firm_db(mongo_client, TENANT_A)
    assert db["carriers"].count_documents({}) == TOTAL - INVALID
    again = upload(client, owner, "carriers", "renamed.csv", content)
    assert again.status_code == 200 and again.headers["Idempotency-Replayed"] == "true"
    assert again.json()["id"] == first["id"] and again.json()["stats"] == done["stats"]
    assert db["carriers"].count_documents({}) == TOTAL - INVALID


def _undo_setup(client: TestClient, mongo_client: MongoClientT, clock: FakeClock,
                headers: dict[str, str]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Import 2 updates and 3 creates; return the committed import and the pre-import documents.

    Args:
        client: Test client.
        mongo_client: Client.
        clock: Fake clock.
        headers: Auth headers.

    Returns:
        (committed import, stored documents of the updated carriers before the import).
    """
    db = firm_db(mongo_client, TENANT_A)
    for index in range(2):
        created(client, headers, "/v1/carriers", {"phone": _phone(index), "name": f"Before {index}",
                                                  "tags": ["keep_me"]})
    before = list(db["carriers"].find({}).sort([("_id", 1)]))
    clock.advance(timedelta(minutes=5))
    rows = [[f"After {index}", _phone(index), str(200000 + index), f"a{index}@fleet.example"] for index in range(5)]
    first = uploaded(client, headers, "carriers", "undo.csv", csv_bytes(CARRIER_HEADER, rows))
    done = committed(client, mongo_client, clock, headers, first["id"], "update")
    assert (done["stats"]["created"], done["stats"]["updated"]) == (3, 2)
    return done, before


def test_undo_within_window_restores_and_removes(client: TestClient, mongo_client: MongoClientT,
                                                 clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    owner = firms.headers("owner")
    done, before = _undo_setup(client, mongo_client, clock, owner)
    db = firm_db(mongo_client, TENANT_A)
    assert one(db, "carriers", {"_id": before[0]["_id"]})["name"] == "After 0"
    clock.advance(timedelta(hours=23))
    owner = fresh_owner(client)
    response = client.post(f"/v1/imports/{done['id']}/undo", headers=owner)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "undone" and body["undo"] == {"restored": 2, "removed": 3, "skipped_modified": 0}
    assert list(db["carriers"].find({}).sort([("_id", 1)])) == before
    assert client.post(f"/v1/imports/{done['id']}/undo", headers=owner).status_code == 409
    events = [event["data"]["status"] for event in db["events"].find({"type": "import.progress"})]
    assert events[-1] == "undone"


def test_undo_after_window_is_409(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    done, _before = _undo_setup(client, mongo_client, clock, firms.headers("owner"))
    clock.advance(timedelta(hours=25))
    response = client.post(f"/v1/imports/{done['id']}/undo", headers=fresh_owner(client))
    assert response.status_code == 409 and error_code(response) == "undo_window_closed"
    assert firm_db(mongo_client, TENANT_A)["carriers"].count_documents({}) == 5


def test_undo_leaves_records_modified_since(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    owner = firms.headers("owner")
    done, before = _undo_setup(client, mongo_client, clock, owner)
    db = firm_db(mongo_client, TENANT_A)
    created_one = one(db, "carriers", {"name": "After 4"})
    clock.advance(timedelta(minutes=1))
    assert client.patch(f"/v1/carriers/{created_one['_id']}", json={"home_base": "Waco, TX"},
                        headers=owner).status_code == 200
    assert client.patch(f"/v1/carriers/{before[1]['_id']}", json={"home_base": "Tyler, TX"},
                        headers=owner).status_code == 200
    body = client.post(f"/v1/imports/{done['id']}/undo", headers=owner).json()
    assert body["undo"] == {"restored": 1, "removed": 2, "skipped_modified": 2}
    assert db["carriers"].count_documents({"_id": created_one["_id"]}) == 1
    assert one(db, "carriers", {"_id": before[1]["_id"]})["name"] == "After 1"
    report = client.get(f"/v1/imports/{done['id']}/report", headers=owner).json()
    assert sorted(row["undo"] for row in report["items"] if row["undo"]) == [
        "removed", "removed", "restored", "skipped_modified", "skipped_modified"]


def test_xlsx_import_with_merged_header_serial_dates_float_phones(client: TestClient, mongo_client: MongoClientT,
                                                                   clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    rows: list[list[Any]] = [["Carrier roster (synthetic)"], ["Carrier", "MC#", "Cell", "Insurance Expires", None],
                             ["Delta Line", 123456.0, 2145550199.0, 46357, None],
                             ["Echo Freight", 654321.0, 4695550198.0, 46360.0, None]]
    content = xlsx_bytes(rows, merges=("A1:E1", "D2:E2"))
    first = uploaded(client, firms.headers("owner"), "carriers", "roster.xlsx", content)
    assert first["columns"] == ["Carrier", "MC#", "Cell", "Insurance Expires", "Insurance Expires 2"]
    assert first["file_type"] == "xlsx" and first["stats"]["valid"] == 2
    committed(client, mongo_client, clock, firms.headers("owner"), first["id"])
    stored = one(firm_db(mongo_client, TENANT_A), "carriers", {"phone": "+12145550199"})
    assert stored["mc_number"] == "123456" and stored["name"] == "Delta Line"
    assert stored["insurance_expires_at"] == datetime(2026, 12, 1, tzinfo=UTC)


def test_vcard_import_maps_first_mobile(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    first = uploaded(client, firms.headers("dispatcher"), "contacts", "contacts.vcf", fixture_bytes("contacts.vcf"))
    assert first["stats"]["valid"] == 3 and first["file_type"] == "vcf"
    committed(client, mongo_client, clock, firms.headers("dispatcher"), first["id"])
    db = firm_db(mongo_client, TENANT_A)
    contacts = {doc["name"]: doc for doc in db["contacts"].find({})}
    assert contacts["Ana Rivera"]["phones"] == ["+12145550131", "+12145550130", "+12145550132"]
    assert contacts["Ben Okafor"]["phones"][0] == "+12145550140"
    assert contacts["Dana Chen"]["phones"][0] == "+12145550152"
    assert contacts["Ana Rivera"]["source"] == "vcard" and contacts["Ana Rivera"]["kind"] == "other"
    assert contacts["Ana Rivera"]["company"] == "Summit Brokerage"


def test_google_contacts_csv_import(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    headers = firms.headers("dispatcher")
    first = uploaded(client, headers, "contacts", "google.csv", fixture_bytes("google_contacts.csv"))
    committed(client, mongo_client, clock, headers, first["id"])
    contacts = {doc["name"]: doc for doc in firm_db(mongo_client, TENANT_A)["contacts"].find({})}
    assert set(contacts) == {"Erin Walsh", "Frank Moreno", "Grace Kim"}
    assert contacts["Frank Moreno"]["emails"] == ["frank@cascade.example", "f.moreno@cascade.example"]
    assert contacts["Frank Moreno"]["phones"] == ["+12145550170", "+12145550171"]
    assert contacts["Erin Walsh"]["title"] == "Account Manager" and contacts["Erin Walsh"]["source"] == "google"


def test_over_size_or_rows_rejected_before_parsing(mongo_client: MongoClientT, clock: FakeClock,
                                                   integrations: Integrations) -> None:
    limits = Settings(env="test", jwt_active_kid=TEST_KID, jwt_keys_json=SecretStr(TEST_KEYS_JSON),
                      import_max_bytes=SMALL_MAX_BYTES, import_max_rows=SMALL_MAX_ROWS)
    with TestClient(create_app(limits, mongo_client, clock=clock, integrations=integrations)) as client:
        owner = seed_firms(client, mongo_client, clock).headers("owner")
        too_big = b"Name,Phone\n" + b"x" * SMALL_MAX_BYTES
        response = upload(client, owner, "carriers", "big.csv", too_big)
        assert response.status_code == 413 and error_code(response) == "file_too_large"
        rows = [[f"c{index}", "2145550100"] for index in range(SMALL_MAX_ROWS + 1)]
        response = upload(client, owner, "carriers", "rows.csv", csv_bytes(("Name", "Phone"), rows))
        assert response.status_code == 422 and error_code(response) == "too_many_rows"
        db = firm_db(mongo_client, TENANT_A)
        assert db["imports"].count_documents({}) == 0 and db["import_rows"].count_documents({}) == 0
        huge = client.post("/v1/imports", data={"entity": "carriers"}, headers=owner,
                           files={"file": ("x.csv", b"a" * (SMALL_MAX_BYTES + 200_000), "text/csv")})
        assert huge.status_code == 413 and error_code(huge) == "payload_too_large"


def test_default_limits_are_the_spec_values() -> None:
    defaults = Settings()
    assert (defaults.import_max_bytes, defaults.import_max_rows, defaults.import_undo_hours) == (
        10 * 1024 * 1024, 20_000, 24)


def test_merge_never_overwrites(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    owner = firms.headers("owner")
    existing = created(client, owner, "/v1/carriers", {"phone": _phone(1), "name": "Keep Me"})
    content = csv_bytes(("Name", "Phone", "Email", "Company"),
                        [["Replace Me", _phone(1), "new@fleet.example", "New Co"]])
    first = uploaded(client, owner, "carriers", "merge.csv", content)
    preview = client.get(f"/v1/imports/{first['id']}/preview?duplicate_strategy=merge", headers=owner).json()
    assert preview["rows"][0]["action"] == "merge"
    done = committed(client, mongo_client, clock, owner, first["id"], "merge")
    assert done["stats"]["merged"] == 1
    stored = one(firm_db(mongo_client, TENANT_A), "carriers", {"phone": existing["phone"]})
    assert stored["name"] == "Keep Me" and stored["email"] == "new@fleet.example" and stored["company"] == "New Co"


def test_duplicate_in_file_skipped(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    owner = firms.headers("owner")
    first = uploaded(client, owner, "carriers", "messy.csv", fixture_bytes("carriers_messy.csv"))
    stats = first["stats"]
    assert (stats["rows"], stats["invalid"], stats["duplicates_in_file"], stats["new"]) == (6, 2, 1, 3)
    preview = client.get(f"/v1/imports/{first['id']}/preview", headers=owner).json()
    by_row = {row["row_no"]: row for row in preview["rows"]}
    assert by_row[8]["action"] == "skip" and by_row[8]["reason"] == "duplicate_in_file"
    assert by_row[7]["errors"][0]["field"] == "phone" and by_row[9]["errors"][0]["field"] == "email"
    done = committed(client, mongo_client, clock, owner, first["id"])
    assert done["stats"]["created"] == 3
    db = firm_db(mongo_client, TENANT_A)
    hal = one(db, "carriers", {"phone": "+14695550120"})
    assert hal["email"] == "hal@coastline.example" and hal["mc_number"] == "0012345"
    assert one(db, "carriers", {"phone": "+14695550121"})["equipment"] == ["flatbed", "step_deck"]


def test_import_progress_events(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    owner = firms.headers("owner")
    rows = [[f"C{index}", _phone(index), "", ""] for index in range(600)]
    first = uploaded(client, owner, "carriers", "events.csv", csv_bytes(CARRIER_HEADER, rows))
    committed(client, mongo_client, clock, owner, first["id"])
    db = firm_db(mongo_client, TENANT_A)
    events = list(db["events"].find({"type": "import.progress"}).sort([("seq", 1)]))
    statuses = [event["data"]["status"] for event in events]
    assert statuses[0] == "committing" and statuses[-1] == "committed" and len(events) >= 4
    done = [event["data"]["done"] for event in events]
    assert done == sorted(done) and done[-1] == 600 and events[-1]["data"]["total"] == 600
    assert all(event["ref"] == {"type": "import", "id": first["id"]} for event in events)


def test_dispatcher_sensitive_terms_are_rejected(client: TestClient, mongo_client: MongoClientT,
                                                 clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    content = csv_bytes(("Name", "Phone", "Dispatch Fee %"), [["Fee Row", _phone(1), "10"], ["Plain", _phone(2), ""]])
    dispatcher = firms.headers("dispatcher")
    first = uploaded(client, dispatcher, "carriers", "fees.csv", content)
    preview = client.get(f"/v1/imports/{first['id']}/preview", headers=dispatcher).json()
    assert preview["rows"][0]["action"] == "skip" and preview["rows"][0]["reason"] == "approval_required"
    assert first["stats"]["needs_approval"] == 1
    done = committed(client, mongo_client, clock, dispatcher, first["id"])
    assert (done["stats"]["created"], done["stats"]["rejected"]) == (1, 1)
    db = firm_db(mongo_client, TENANT_A)
    assert db["carriers"].count_documents({"name": "Fee Row"}) == 0
    report = client.get(f"/v1/imports/{first['id']}/report", headers=dispatcher).json()
    assert report["items"][0]["outcome"] == "rejected" and report["items"][0]["reason"] == "approval_required"
    owner = firms.headers("owner")
    owned = uploaded(client, owner, "carriers", "fees.csv", csv_bytes(("Name", "Phone", "Fee"),
                                                                      [["Fee Row", _phone(1), "10"]]))
    committed(client, mongo_client, clock, owner, owned["id"])
    assert one(db, "carriers", {"name": "Fee Row"})["dispatch_fee_pct"] == 10.0


def test_consent_columns_are_never_imported(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    owner = firms.headers("owner")
    first = uploaded(client, owner, "carriers", "carriers.csv", fixture_bytes("carriers.csv"))
    assert first["ignored_consent_columns"] == ["SMS Consent"] and first["mapping"]["SMS Consent"] is None
    bad = client.put(f"/v1/imports/{first['id']}/mapping", headers=owner,
                     json={"mapping": {**first["mapping"], "SMS Consent": "consent"}})
    assert bad.status_code == 422 and error_code(bad) == "field_not_importable"
    committed(client, mongo_client, clock, owner, first["id"])
    db = firm_db(mongo_client, TENANT_A)
    assert db["carriers"].count_documents({}) == 5
    assert db["carriers"].count_documents({"consent": {"$exists": True}}) == 0
    assert db["consent_events"].count_documents({}) == 0
    lone = one(db, "carriers", {"phone": "+12145550110"})
    assert lone["equipment"] == ["dry_van", "reefer"] and lone["mc_number"] == "100001"


def test_imported_writes_are_audited_as_import(client: TestClient, mongo_client: MongoClientT,
                                               clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    owner = firms.headers("owner")
    first = uploaded(client, owner, "carriers", "carriers.csv", fixture_bytes("carriers.csv"))
    committed(client, mongo_client, clock, owner, first["id"])
    db = firm_db(mongo_client, TENANT_A)
    audits = list(db["audit"].find({"event": "carrier.create"}))
    assert len(audits) == 5 and all(row["who"]["kind"] == "import" for row in audits)
    assert all(row["who"]["id"] == first["id"] for row in audits)
    carrier = one(db, "carriers", {})
    assert carrier["created_by"]["kind"] == "import" and carrier["created_by"]["user_id"]


def test_mapping_route_validation(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    owner = firms.headers("owner")
    content = csv_bytes(("Who", "Number", "Mail"), [["A", _phone(1), "a@x.example"]])
    first = uploaded(client, owner, "carriers", "odd.csv", content)
    assert first["status"] == "uploaded" and first["unmapped_required"] == ["phone"]
    assert client.get(f"/v1/imports/{first['id']}/preview", headers=owner).status_code == 409
    assert error_code(commit(client, owner, first["id"])) == "mapping_required"
    path = f"/v1/imports/{first['id']}/mapping"
    cases = [({"Nope": "phone"}, "unknown_column"), ({"Number": "dispatch_fee"}, "unknown_field"),
             ({"Number": "phone", "Who": "phone"}, "duplicate_field"), ({"Who": "name"}, "required_field_unmapped")]
    for body, code in cases:
        response = client.put(path, json={"mapping": body}, headers=owner)
        assert response.status_code == 422 and error_code(response) == code, body
    assert client.put(path, json={"mapping": "x"}, headers=owner).status_code == 422
    good = client.put(path, json={"mapping": {"Who": "name", "Number": "phone", "Mail": "email"}}, headers=owner)
    assert good.status_code == 200 and good.json()["status"] == "mapped" and good.json()["stats"]["new"] == 1


def test_templates_round_trip_through_suggestions(client: TestClient, mongo_client: MongoClientT,
                                                  clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    for entity in ("carriers", "drivers", "brokers", "contacts"):
        response = client.get(f"/v1/imports/templates/{entity}", headers=firms.headers("viewer"))
        assert response.status_code == 200 and response.headers["content-type"].startswith("text/csv")
        assert f"{entity}-template.csv" in response.headers["content-disposition"]
        first = uploaded(client, firms.headers("owner"), entity, f"{entity}.csv", response.content + b"\n")
        assert None not in first["mapping"].values(), (entity, first["mapping"])
    assert client.get("/v1/imports/templates/loads", headers=firms.headers("viewer")).status_code == 422
    assert client.get("/v1/imports/templates/carriers").status_code == 401


def test_drivers_and_brokers_import(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    owner = firms.headers("owner")
    carrier = created(client, owner, "/v1/carriers", CARRIER)
    created(client, owner, "/v1/brokers", {"mc_number": "777001", "company": "Old Name"})
    drivers = csv_bytes(("Driver Name", "Driver Phone", "Carrier Phone"),
                        [["Sam", "2145550900", CARRIER["phone"]], ["Nope", "2145550901", "2145550999"]])
    first = uploaded(client, owner, "drivers", "drivers.csv", drivers)
    assert (first["stats"]["valid"], first["stats"]["invalid"]) == (1, 1)
    committed(client, mongo_client, clock, owner, first["id"])
    db = firm_db(mongo_client, TENANT_A)
    assert one(db, "drivers", {"phone": "+12145550900"})["carrier_id"] == carrier["id"]
    brokers = csv_bytes(("MC", "Broker", "Payment Terms"), [["MC-777001", "New Name", "Net 30"],
                                                            ["777002", "Fresh", ""]])
    second = uploaded(client, owner, "brokers", "brokers.csv", brokers)
    assert (second["stats"]["existing"], second["stats"]["new"]) == (1, 1)
    committed(client, mongo_client, clock, owner, second["id"])
    assert one(db, "brokers", {"mc_number": "777001"})["company"] == "New Name"
    assert one(db, "brokers", {"mc_number": "777002"})["tags"] == []


def test_upload_type_and_entity_refusals(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    owner = firms.headers("owner")
    assert upload(client, owner, "carriers", "x.exe", b"MZ").status_code == 415
    assert error_code(upload(client, owner, "carriers", "x.vcf", fixture_bytes("contacts.vcf"))) == \
        "vcard_contacts_only"
    assert upload(client, owner, "loads", "x.csv", b"a,b\n").status_code == 422
    assert client.post("/v1/imports", data={"entity": "carriers"}, headers=owner).status_code == 422
    assert client.post("/v1/imports", content=b"{}", headers={**owner, "Content-Type": "application/json"}
                       ).status_code == 422
    missing = upload(client, owner, "carriers", "empty.csv", b"")
    assert missing.status_code == 422 and error_code(missing) == "no_header"


def test_commit_is_pollable_and_replayed(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    owner = firms.headers("owner")
    first = uploaded(client, owner, "carriers", "carriers.csv", fixture_bytes("carriers.csv"))
    response = commit(client, owner, first["id"], "skip")
    assert response.status_code == 202 and response.json()["status"] == "committing"
    replay = commit(client, owner, first["id"], "merge")
    assert replay.status_code == 200 and replay.headers["Idempotency-Replayed"] == "true"
    assert replay.json()["duplicate_strategy"] == "skip"
    assert run_jobs(mongo_client, clock) == 1 and run_jobs(mongo_client, clock) == 0
    assert client.get(f"/v1/imports/{first['id']}", headers=owner).json()["status"] == "committed"
    assert client.put(f"/v1/imports/{first['id']}/mapping", json={"mapping": first["mapping"]},
                      headers=owner).status_code == 409
    bad = client.post(f"/v1/imports/{first['id']}/commit", json={"duplicate_strategy": "replace"}, headers=owner)
    assert bad.status_code == 422


def test_report_json_and_csv(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    owner = firms.headers("owner")
    first = uploaded(client, owner, "carriers", "messy.csv", fixture_bytes("carriers_messy.csv"))
    page = client.get(f"/v1/imports/{first['id']}/report?limit=4", headers=owner).json()
    assert len(page["items"]) == 4 and page["next_cursor"]
    rest = client.get(f"/v1/imports/{first['id']}/report?limit=4&cursor={page['next_cursor']}", headers=owner).json()
    assert len(rest["items"]) == 2 and rest["next_cursor"] is None
    report = client.get(f"/v1/imports/{first['id']}/report?format=csv", headers=firms.headers("viewer"))
    assert report.status_code == 200 and report.headers["content-type"].startswith("text/csv")
    text = report.text
    assert "'=HYPERLINK" in text and "duplicate_in_file" in text and "\n=HYPERLINK" not in text


def test_list_imports_newest_first(client: TestClient, mongo_client: MongoClientT, clock: FakeClock) -> None:
    firms = seed_firms(client, mongo_client, clock)
    owner = firms.headers("owner")
    first = uploaded(client, owner, "carriers", "carriers.csv", fixture_bytes("carriers.csv"))
    second = uploaded(client, owner, "contacts", "contacts.vcf", fixture_bytes("contacts.vcf"))
    page = client.get("/v1/imports?limit=1", headers=firms.headers("viewer")).json()
    assert [item["id"] for item in page["items"]] == [second["id"]]
    rest = client.get(f"/v1/imports?limit=1&cursor={page['next_cursor']}", headers=owner).json()
    assert [item["id"] for item in rest["items"]] == [first["id"]]
    assert client.get("/v1/imports", headers=firms.headers("owner_b")).json()["items"] == []
