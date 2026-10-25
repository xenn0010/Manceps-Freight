"""Helpers for import and export tests: fixture files, uploads, synthetic spreadsheets and the worker pass."""

from __future__ import annotations

import csv
import io
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import httpx2
from authkit import PHONE_OWNER_A, bearer, otp_login, platform
from conftest import FakeClock
from fastapi.testclient import TestClient
from openpyxl import Workbook

from manceps_api.exports.store import ExportStore
from manceps_core.mongo import MongoClientT
from manceps_core.tenancy import TenantDb
from manceps_worker.jobs import run_firm_jobs

FIXTURES = Path(__file__).resolve().parent / "fixtures"
CSV_TYPE = "text/csv"


def fixture_bytes(name: str) -> bytes:
    """Read a committed fixture file.

    Args:
        name: File name under tests/fixtures.

    Returns:
        The bytes.
    """
    return (FIXTURES / name).read_bytes()


def upload(client: TestClient, headers: dict[str, str], entity: str, filename: str,
           content: bytes) -> httpx2.Response:
    """POST a file to /v1/imports.

    Args:
        client: Test client.
        headers: Auth headers.
        entity: Entity name.
        filename: File name sent in the multipart part.
        content: File bytes.

    Returns:
        The response.
    """
    return client.post("/v1/imports", data={"entity": entity}, files={"file": (filename, content, CSV_TYPE)},
                       headers=headers)


def uploaded(client: TestClient, headers: dict[str, str], entity: str, filename: str,
             content: bytes) -> dict[str, Any]:
    """Upload and expect 201.

    Args:
        client: Test client.
        headers: Auth headers.
        entity: Entity name.
        filename: File name.
        content: File bytes.

    Returns:
        The import body.
    """
    response = upload(client, headers, entity, filename, content)
    assert response.status_code == 201, response.text
    return response.json()


def csv_bytes(header: Sequence[str], rows: Sequence[Sequence[Any]]) -> bytes:
    """Render a CSV file.

    Args:
        header: Column names.
        rows: Data rows.

    Returns:
        UTF-8 bytes.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def xlsx_bytes(rows: Sequence[Sequence[Any]], merges: Sequence[str] = ()) -> bytes:
    """Render a one-sheet workbook.

    Args:
        rows: Rows of cell values.
        merges: Ranges to merge, e.g. "A1:C1".

    Returns:
        The XLSX bytes.
    """
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    for row in rows:
        sheet.append(list(row))
    for cell_range in merges:
        sheet.merge_cells(cell_range)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def commit(client: TestClient, headers: dict[str, str], import_id: str, strategy: str = "update") -> httpx2.Response:
    """POST the commit request.

    Args:
        client: Test client.
        headers: Auth headers.
        import_id: Import id.
        strategy: skip, update or merge.

    Returns:
        The response.
    """
    return client.post(f"/v1/imports/{import_id}/commit", json={"duplicate_strategy": strategy}, headers=headers)


def run_jobs(mongo_client: MongoClientT, clock: FakeClock, store: ExportStore | None = None) -> int:
    """Run one worker pass over every active firm (import commits and exports).

    Args:
        mongo_client: Client.
        clock: Fake clock.
        store: Export store, or None.

    Returns:
        Number of jobs finished.
    """
    return run_firm_jobs(platform(mongo_client), TenantDb(mongo_client), clock, store)


def committed(client: TestClient, mongo_client: MongoClientT, clock: FakeClock, headers: dict[str, str],
              import_id: str, strategy: str = "update") -> dict[str, Any]:
    """Request a commit, run the worker and return the finished import.

    Args:
        client: Test client.
        mongo_client: Client.
        clock: Fake clock.
        headers: Auth headers.
        import_id: Import id.
        strategy: Duplicate strategy.

    Returns:
        The import after the worker pass.
    """
    response = commit(client, headers, import_id, strategy)
    assert response.status_code == 202, response.text
    run_jobs(mongo_client, clock)
    final = client.get(f"/v1/imports/{import_id}", headers=headers)
    assert final.status_code == 200, final.text
    return final.json()


def fresh_owner(client: TestClient) -> dict[str, str]:
    """Sign firm A's owner in again (after the fake clock moved past the access-token lifetime).

    Args:
        client: Test client.

    Returns:
        Authorization headers.
    """
    return bearer(str(otp_login(client, PHONE_OWNER_A)["access_token"]))
