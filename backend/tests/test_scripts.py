"""Tooling scripts: OpenAPI export check, vendoring check, key generation; core layering."""

from __future__ import annotations

import ast
import base64
import json
import shutil
import sys
from pathlib import Path

import jwt
import pytest
from conftest import BACKEND_DIR, load_module
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key, load_pem_public_key

SCRIPTS = BACKEND_DIR / "scripts"
CORE_DIR = BACKEND_DIR / "manceps_core"
CORE_ALLOWED_THIRD_PARTY = {"pymongo", "bson"}
SECRETS_KEY_BYTES = 32

export_openapi = load_module("script_export_openapi", SCRIPTS / "export_openapi.py")
vendor_core = load_module("script_vendor_core", SCRIPTS / "vendor_core.py")
gen_keys = load_module("script_gen_keys", SCRIPTS / "gen_keys.py")


def test_openapi_export_check_fails_when_stale(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """--check fails on a stale or missing file and passes after regeneration."""
    target = tmp_path / "openapi.json"
    assert export_openapi.main(["--check", "--output", str(target)]) == 1
    target.write_text('{"openapi": "3.1.0", "paths": {}}\n', encoding="utf-8")
    assert export_openapi.main(["--check", "--output", str(target)]) == 1
    assert "stale" in capsys.readouterr().err
    assert export_openapi.main(["--output", str(target)]) == 0
    assert export_openapi.main(["--check", "--output", str(target)]) == 0
    schema = json.loads(target.read_text(encoding="utf-8"))
    assert "/healthz" in schema["paths"]


def test_committed_openapi_is_current() -> None:
    """The committed backend/openapi.json matches the app."""
    assert export_openapi.main(["--check"]) == 0


def _copy_core(tmp_path: Path) -> tuple[Path, Path]:
    """Make a scratch source package and an empty destination.

    Args:
        tmp_path: Pytest temp dir.

    Returns:
        Source and destination directories.
    """
    source = tmp_path / "src" / "manceps_core"
    shutil.copytree(CORE_DIR, source, ignore=shutil.ignore_patterns("__pycache__"))
    (source / "__pycache__").mkdir()
    (source / "__pycache__" / "x.cpython.pyc").write_bytes(b"\x00")
    return source, tmp_path / "plugin" / "_vendor" / "manceps_core"


def test_vendor_core_sync_and_check(tmp_path: Path) -> None:
    """Sync copies sources only; --check detects edits, extra files and missing files."""
    source, dest = _copy_core(tmp_path)
    args = ["--source", str(source), "--dest", str(dest)]
    assert vendor_core.main(["--check", *args]) == 1
    assert vendor_core.main(args) == 0
    assert vendor_core.main(["--check", *args]) == 0
    assert not (dest / "__pycache__").exists()

    (dest / "tenancy.py").write_text("# drift\n", encoding="utf-8")
    assert vendor_core.main(["--check", *args]) == 1
    assert vendor_core.main(args) == 0
    (dest / "extra.py").write_text("X = 1\n", encoding="utf-8")
    assert vendor_core.main(["--check", *args]) == 1
    assert vendor_core.main(args) == 0
    assert not (dest / "extra.py").exists()
    assert vendor_core.main(["--check", *args]) == 0


def test_vendor_core_refuses_missing_source(tmp_path: Path) -> None:
    """A missing source directory is an error, never an empty vendored copy."""
    assert vendor_core.main(["--source", str(tmp_path / "nope"), "--dest", str(tmp_path / "out")]) == 2


def test_committed_vendor_copy_is_current() -> None:
    """The plugin's vendored manceps_core matches backend/manceps_core."""
    assert vendor_core.main(["--check"]) == 0


def test_gen_keys_prints_usable_keys(capsys: pytest.CaptureFixture[str]) -> None:
    """The generated key pair signs and verifies EdDSA JWTs; SECRETS_KEY is 32 random bytes."""
    assert gen_keys.main() == 0
    out = json.loads(capsys.readouterr().out)
    kid = out["JWT_ACTIVE_KID"]
    keys = json.loads(out["JWT_KEYS_JSON"])
    private = load_pem_private_key(keys[kid]["private_pem"].encode(), password=None)
    public = load_pem_public_key(keys[kid]["public_pem"].encode())
    assert isinstance(private, Ed25519PrivateKey) and isinstance(public, Ed25519PublicKey)
    token = jwt.encode({"sub": "u1"}, private, algorithm="EdDSA", headers={"kid": kid})
    assert jwt.decode(token, public, algorithms=["EdDSA"])["sub"] == "u1"
    assert len(base64.urlsafe_b64decode(out["SECRETS_KEY"])) == SECRETS_KEY_BYTES


def _imported_roots(path: Path) -> set[str]:
    """List the absolute top-level modules a file imports.

    Args:
        path: Python file.

    Returns:
        Top-level module names.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_core_is_vendorable() -> None:
    """manceps_core imports only the stdlib, pymongo/bson and itself (relatively), so the plugin can vendor it."""
    allowed = set(sys.stdlib_module_names) | CORE_ALLOWED_THIRD_PARTY | {"__future__"}
    for path in CORE_DIR.rglob("*.py"):
        assert _imported_roots(path) <= allowed, path
