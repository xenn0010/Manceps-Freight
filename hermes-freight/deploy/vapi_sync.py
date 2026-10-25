"""Push the Manceps voice assistants in `vapi/*.json` to the firm's Vapi org.

The inbound assistant (answers the dispatch line) is updated in place; the broker caller
(outbound negotiation, never accepts a rate) is created on first sync and updated after.
Every assistant must disclose that it is an AI and that the call may be recorded, and the
key must belong to the org that owns the dispatch number, or nothing is written.

Run on the laptop or gateway host with the org's private key in VAPI_API_KEY:
    python3 vapi_sync.py           # validate the configs only (dry run)
    python3 vapi_sync.py --apply   # push them and record the ids in vapi/deployed.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

API_BASE = "https://api.vapi.ai"
USER_AGENT = "manceps-vapi-sync/1.0"
TIMEOUT_SECONDS = 20
ERROR_CHARS = 300
NOT_FOUND = 404
EXIT_CONFIG = 2
EXIT_VAPI = 1

VAPI_DIR = Path(__file__).resolve().parent.parent / "vapi"
DEPLOYED_FILE = VAPI_DIR / "deployed.json"
CONFIG_FILES = {"inbound": "assistant.json", "broker_caller": "broker_caller.json"}
ID_KEYS = {"inbound": "assistant_id", "broker_caller": "broker_caller_assistant_id"}
BROKER_CALLER_VARIABLES = (
    "firm_name", "load_ref", "lane", "pickup_date", "equipment", "carrier_name",
    "posted_rate", "target_rate", "floor_rate",
)
AI_WORD = re.compile(r"\bAI\b")
RECORDING_WORD = re.compile(r"\brecorded\b", re.IGNORECASE)

Json = dict[str, Any]
Transport = Callable[[str, str, Json | None], Json]


class VapiError(RuntimeError):
    """A Vapi API request failed or the key points at the wrong org."""

    def __init__(self, status: int, message: str) -> None:
        """Store the HTTP status with the message.

        Args:
            status: HTTP status code, or 0 for a network failure.
            message: Short description, never containing the key.
        """
        super().__init__(f"Vapi {status}: {message}")
        self.status = status


def load_configs() -> dict[str, Json]:
    """Read every assistant config shipped in `vapi/`.

    Returns:
        Config by assistant role (`inbound`, `broker_caller`).
    """
    return {role: json.loads((VAPI_DIR / name).read_text()) for role, name in CONFIG_FILES.items()}


def check_disclosure(config: Json) -> None:
    """Refuse an assistant whose greeting hides that it is an AI or that calls are recorded.

    Args:
        config: Assistant config.

    Raises:
        ValueError: If the first message lacks the AI or recording disclosure.
    """
    first = str(config.get("firstMessage", ""))
    if not AI_WORD.search(first):
        raise ValueError(f"{config.get('name')}: firstMessage must say it is an AI")
    if not RECORDING_WORD.search(first):
        raise ValueError(f"{config.get('name')}: firstMessage must say the call may be recorded")


def http_transport(api_key: str) -> Transport:
    """Build a transport that calls the Vapi REST API.

    Args:
        api_key: The org's private API key.

    Returns:
        A function sending (method, path, body) and returning the JSON response.
    """
    headers = {"Authorization": f"Bearer {api_key}", "User-Agent": USER_AGENT, "Content-Type": "application/json"}

    def send(method: str, path: str, body: Json | None) -> Json:
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(API_BASE + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                return json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as exc:
            raise VapiError(exc.code, exc.read()[:ERROR_CHARS].decode(errors="replace")) from exc
        except urllib.error.URLError as exc:
            raise VapiError(0, str(exc.reason)) from exc

    return send


def _check_org(transport: Transport, deployed: Json) -> None:
    """Confirm the key's org owns the dispatch number before writing anything.

    Args:
        transport: Vapi transport.
        deployed: Recorded ids, including `phone_number_id`.

    Raises:
        VapiError: If the number is not visible with this key.
    """
    try:
        transport("GET", f"/phone-number/{deployed['phone_number_id']}", None)
    except VapiError as exc:
        if exc.status == NOT_FOUND:
            raise VapiError(NOT_FOUND, "this key belongs to another Vapi org than the dispatch number") from exc
        raise


def sync(transport: Transport, deployed: Json, configs: dict[str, Json]) -> Json:
    """Create or update each assistant and return the updated id record.

    Args:
        transport: Vapi transport.
        deployed: Recorded ids (`phone_number_id`, `assistant_id`, optional `broker_caller_assistant_id`).
        configs: Config by assistant role.

    Returns:
        The id record with any newly created assistant ids.

    Raises:
        ValueError: If a config lacks the disclosure (checked before any request).
        VapiError: If the key is for another org or a request fails.
    """
    for config in configs.values():
        check_disclosure(config)
    _check_org(transport, deployed)
    updated = dict(deployed)
    for role, config in configs.items():
        id_key = ID_KEYS[role]
        if updated.get(id_key):
            transport("PATCH", f"/assistant/{updated[id_key]}", config)
        else:
            updated[id_key] = transport("POST", "/assistant", config)["id"]
    return updated


def main(argv: Sequence[str] | None = None) -> int:
    """Validate the configs and, with --apply, push them to Vapi.

    Args:
        argv: Command-line arguments (defaults to sys.argv).

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="push the assistants to Vapi")
    args = parser.parse_args(argv)
    api_key = os.environ.get("VAPI_API_KEY")
    if not api_key:
        print("VAPI_API_KEY is not set", file=sys.stderr)
        return EXIT_CONFIG
    configs = load_configs()
    try:
        for config in configs.values():
            check_disclosure(config)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return EXIT_CONFIG
    if not args.apply:
        print(f"dry run: {', '.join(c['name'] for c in configs.values())} are valid; pass --apply to push")
        return 0
    deployed = json.loads(DEPLOYED_FILE.read_text())
    try:
        updated = sync(http_transport(api_key), deployed, configs)
    except VapiError as exc:
        print(exc, file=sys.stderr)
        return EXIT_VAPI
    DEPLOYED_FILE.write_text(json.dumps(updated, indent=2) + "\n")
    print("synced: " + ", ".join(f"{role}={updated[ID_KEYS[role]]}" for role in configs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
