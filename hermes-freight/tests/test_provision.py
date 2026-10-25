"""Provisioning helpers: URI credential swap and profile .env handling."""

from __future__ import annotations

import importlib.util
import stat
import urllib.parse
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "deploy" / "provision_tenant.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("provision_tenant", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


provision = _load()


def test_with_credentials_swaps_only_userinfo() -> None:
    base = "mongodb+srv://operator:op%40ss@cluster0.abc.mongodb.net/?retryWrites=true&appName=Cluster0"
    uri = provision.with_credentials(base, "firm-apex-freight", "p@ss/word:1")
    parts = urllib.parse.urlsplit(uri)
    assert parts.scheme == "mongodb+srv"
    assert parts.hostname == "cluster0.abc.mongodb.net"
    assert parts.query == "retryWrites=true&appName=Cluster0"
    assert urllib.parse.unquote(parts.username or "") == "firm-apex-freight"
    assert urllib.parse.unquote(parts.password or "") == "p@ss/word:1"
    assert "operator" not in uri


def test_upsert_env_replaces_keys_and_locks_file(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("KEEP=1\nFREIGHT_TENANT_ID=old\n# comment\n")
    provision.upsert_env(env, {"FREIGHT_TENANT_ID": "apex-freight", "MONGODB_URI": "mongodb://x"})
    values = provision.read_env(env)
    assert values == {"KEEP": "1", "FREIGHT_TENANT_ID": "apex-freight", "MONGODB_URI": "mongodb://x"}
    assert stat.S_IMODE(env.stat().st_mode) == 0o600


def test_read_env_strips_quotes_and_ignores_comments(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("A='one'\nB=\"two\"\n#C=3\n\nnot a pair\n")
    assert provision.read_env(env) == {"A": "one", "B": "two"}


def test_provision_shared_uses_operator_uri(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(provision, "HERMES_HOME", tmp_path)
    (tmp_path / ".env").write_text("MONGODB_URI=mongodb://operator@cluster\n")
    monkeypatch.setattr(provision, "wait_for_access", lambda uri, tid: calls.append(("wait", uri, tid)))
    monkeypatch.setattr(provision, "configure_profile",
                        lambda tid, uri, phone: calls.append(("configure", tid, uri, phone)) or tmp_path / tid)
    out = provision.provision("apex-freight", "+12405550100", shared_credentials=True)
    assert out == tmp_path / "apex-freight"
    assert calls == [("wait", "mongodb://operator@cluster", "apex-freight"),
                     ("configure", "apex-freight", "mongodb://operator@cluster", "+12405550100")]


def test_provision_rejects_bad_tenant_before_any_work(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(provision, "wait_for_access", lambda *a: pytest.fail("must not run"))
    with pytest.raises(provision.tenant.TenantError):
        provision.provision("Bad Id!", "+12405550100", shared_credentials=True)


def test_scoped_user_requires_atlas_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in provision.ATLAS_ENV:
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(RuntimeError, match="ATLAS_PUBLIC_KEY"):
        provision.create_scoped_user("apex-freight")
