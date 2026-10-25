"""Phase 4 backend tests: voice/* endpoints with no keys configured."""
import os
import requests
import pytest

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get("REACT_APP_BACKEND_URL") else None

# Read frontend .env as fallback for backend URL
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break


def test_openapi_available():
    r = requests.get(f"{BASE_URL}/api/openapi.json", timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert "paths" in data
    # verify voice routes exist
    assert "/api/voice/config" in data["paths"]
    assert "/api/voice/calls" in data["paths"]


def test_voice_config_not_configured():
    r = requests.get(f"{BASE_URL}/api/voice/config", timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert data.get("configured") is False


def test_voice_calls_not_configured_rejects():
    body = {
        "contact": {"id": "D-101", "name": "Ava Reed", "role": "driver", "phone": "+16093021443"},
        "task": {
            "type": "driver_booking",
            "objective": "Confirm booking",
            "facts": ["Load O-1"],
            "allowedOutcomes": ["confirmed", "declined"],
            "firstMessage": "Hi Ava, FreightOS here.",
            "schema": {"type": "object", "properties": {}},
        },
        "linked": {"loadId": "O-1"},
        "idempotencyKey": "test-key-1",
    }
    r = requests.post(f"{BASE_URL}/api/voice/calls", json=body, timeout=15)
    # Must NOT dial; expect 4xx/503
    assert r.status_code in (400, 401, 403, 422, 500, 502, 503), f"unexpected {r.status_code}: {r.text[:200]}"
    # 503 "not configured" is the expected path
    assert r.status_code == 503 or "configured" in r.text.lower() or "not" in r.text.lower()
