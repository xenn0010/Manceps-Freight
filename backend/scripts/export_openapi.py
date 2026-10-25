"""Write the API's OpenAPI schema to backend/openapi.json, or verify the committed copy with --check.

Usage (working directory backend/):
    uv run python scripts/export_openapi.py           # regenerate
    uv run python scripts/export_openapi.py --check   # exit 1 if the committed file is stale
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from pymongo import MongoClient

from manceps_api.app import create_app
from manceps_api.settings import Settings
from manceps_core.mongo import Doc

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = BACKEND_DIR / "openapi.json"
JSON_INDENT = 2
OFFLINE_URI = "mongodb://127.0.0.1:27017"
EXIT_OK = 0
EXIT_STALE = 1


def render_schema() -> str:
    """Generate the schema text deterministically, without touching a database.

    Returns:
        Pretty-printed JSON with sorted keys and a trailing newline.
    """
    client = MongoClient[Doc](OFFLINE_URI, connect=False)
    try:
        schema = create_app(Settings(env="dev"), client).openapi()
    finally:
        client.close()
    return json.dumps(schema, indent=JSON_INDENT, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    """Export or check the schema.

    Args:
        argv: Command-line arguments (defaults to sys.argv).

    Returns:
        0 on success, 1 when --check finds a stale or missing file.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the file differs from the generated schema")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="schema file path")
    args = parser.parse_args(argv)
    output: Path = args.output
    expected = render_schema()
    if args.check:
        current = output.read_text(encoding="utf-8") if output.exists() else None
        if current != expected:
            print(f"{output} is stale; run scripts/export_openapi.py", file=sys.stderr)
            return EXIT_STALE
        print(f"{output} is up to date")
        return EXIT_OK
    output.write_text(expected, encoding="utf-8")
    print(f"wrote {output}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
