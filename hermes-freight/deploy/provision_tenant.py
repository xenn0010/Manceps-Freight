"""Provision a dispatch firm: Hermes profile, scoped MongoDB user, secrets, and identity.

Run as the operator on the gateway host, where `hermes` is installed:

    python3 provision_tenant.py apex-freight --dispatcher-phone 240-555-0100

Database credentials, in order of preference:
  scoped (default): creates an Atlas database user that can only read and write
      firm_<tenant>. Needs ATLAS_PUBLIC_KEY, ATLAS_PRIVATE_KEY, ATLAS_GROUP_ID, and
      ATLAS_CLUSTER in the environment (an Atlas programmatic API key, Project Owner).
  --shared-credentials: reuses the operator's MONGODB_URI. Isolation is then enforced
      only by the plugin code, not by the database. Acceptable for a single pilot firm.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from types import ModuleType

import pymongo
import pymongo.errors
from ruamel.yaml import YAML

PLUGIN_DIR = Path(__file__).resolve().parent.parent
PLUGIN_NAME = "hermes-freight"
PLUGIN_COPY_IGNORE = shutil.ignore_patterns("__pycache__", "tests", "vapi", ".pytest_cache")

ATLAS_API = "https://cloud.mongodb.com/api/atlas/v2"
ATLAS_ACCEPT = "application/vnd.atlas.2023-01-01+json"
ATLAS_ENV = ("ATLAS_PUBLIC_KEY", "ATLAS_PRIVATE_KEY", "ATLAS_GROUP_ID", "ATLAS_CLUSTER")
HTTP_TIMEOUT_SECONDS = 30
REFERENCE_DB = "freight_reference"
PASSWORD_BYTES = 24
PROPAGATION_TIMEOUT_SECONDS = 120
PROPAGATION_POLL_SECONDS = 5
HERMES_HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
MANAGED_CONFIG = Path(os.environ.get("HERMES_MANAGED_DIR", "/etc/hermes")) / "config.yaml"
INHERITED_KEYS = ("ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY", "FMCSA_WEBKEY", "EIA_API_KEY", "GOOGLE_MAPS_API_KEY",
                  "ORS_API_KEY", "FREIGHT_CONTACT_EMAIL")
AUX_TASKS = ("compression", "title_generation", "tts_audio_tags", "skills_hub", "mcp", "triage_specifier")
INHERITED_CONFIG = ("model.provider", "model.default", "fallback_providers",
                    *(f"auxiliary.{task}.{field}" for task in AUX_TASKS for field in ("provider", "model")))
ISOLATION_CONFIG = {
    "plugins.isolation": "host",
    "agent.disabled_toolsets": json.dumps(["terminal", "file", "code_execution"]),
}


def _load_tenant_module() -> ModuleType:
    """Import the plugin's tenant module for id validation and naming.

    Returns:
        The tenant module.

    Raises:
        RuntimeError: If tenant.py cannot be loaded.
    """
    spec = importlib.util.spec_from_file_location("hermes_freight_tenant", PLUGIN_DIR / "tenant.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load tenant.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(module)
    return module


tenant = _load_tenant_module()


def hermes(*args: str) -> str:
    """Run a hermes CLI command and return stdout.

    Args:
        *args: Arguments after `hermes`.

    Returns:
        Captured stdout.

    Raises:
        RuntimeError: If the command fails.
    """
    proc = subprocess.run(["hermes", *args], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if proc.returncode != 0:
        raise RuntimeError(f"hermes {' '.join(args[:3])} failed: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc.stdout


def read_env(path: Path) -> dict[str, str]:
    """Parse a dotenv file into a dict (simple KEY=VALUE lines, quotes stripped).

    Args:
        path: File to read.

    Returns:
        Parsed values; empty if the file is missing.
    """
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text().splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() and not key.lstrip().startswith("#"):
            values[key.strip()] = value.strip().strip("'\"")
    return values


def upsert_env(path: Path, updates: dict[str, str]) -> None:
    """Set keys in a dotenv file, keeping other lines, with owner-only permissions.

    Args:
        path: Profile .env file.
        updates: Keys and values to set.
    """
    lines = path.read_text().splitlines() if path.exists() else []
    lines = [ln for ln in lines if ln.partition("=")[0].strip() not in updates]
    lines += [f"{key}={value}" for key, value in updates.items()]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    path.chmod(0o600)


def atlas_request(method: str, path: str, body: dict[str, object] | None = None) -> dict[str, object]:
    """Call the Atlas Admin API with digest authentication.

    Args:
        method: HTTP method.
        path: Path under /api/atlas/v2.
        body: JSON body, if any.

    Returns:
        Decoded JSON response.

    Raises:
        RuntimeError: On HTTP errors, with Atlas's error detail.
    """
    url = ATLAS_API + path
    manager = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    manager.add_password(None, url, os.environ["ATLAS_PUBLIC_KEY"], os.environ["ATLAS_PRIVATE_KEY"])
    opener = urllib.request.build_opener(urllib.request.HTTPDigestAuthHandler(manager))
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method,
                                     headers={"Accept": ATLAS_ACCEPT, "Content-Type": "application/json"})
    try:
        with opener.open(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            return json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Atlas API {method} {path}: {exc.code} {exc.read().decode(errors='replace')}") from exc


def create_scoped_user(tenant_id: str) -> tuple[str, str]:
    """Create an Atlas database user limited to readWrite on the firm's database.

    Args:
        tenant_id: Valid tenant id.

    Returns:
        Username and generated password.

    Raises:
        RuntimeError: If Atlas credentials are missing or the API call fails.
    """
    missing = [name for name in ATLAS_ENV if not os.environ.get(name)]
    if missing:
        raise RuntimeError(f"scoped credentials need {', '.join(missing)}; or pass --shared-credentials")
    username = f"firm-{tenant_id}"
    password = secrets.token_urlsafe(PASSWORD_BYTES)
    group = os.environ["ATLAS_GROUP_ID"]
    atlas_request("POST", f"/groups/{group}/databaseUsers", {
        "databaseName": "admin", "groupId": group, "username": username, "password": password,
        "roles": [{"databaseName": tenant.database_name(tenant_id), "roleName": "readWrite"},
                  {"databaseName": REFERENCE_DB, "roleName": "read"}],
        "scopes": [{"name": os.environ["ATLAS_CLUSTER"], "type": "CLUSTER"}],
    })
    return username, password


def with_credentials(base_uri: str, username: str, password: str) -> str:
    """Swap the user and password in a MongoDB URI, keeping host and options.

    Args:
        base_uri: Operator connection string.
        username: New user.
        password: New password.

    Returns:
        Connection string for the new user.
    """
    parts = urllib.parse.urlsplit(base_uri)
    host = parts.netloc.rpartition("@")[2]
    userinfo = f"{urllib.parse.quote(username, safe='')}:{urllib.parse.quote(password, safe='')}"
    return urllib.parse.urlunsplit((parts.scheme, f"{userinfo}@{host}", parts.path or "/", parts.query, ""))


def wait_for_access(uri: str, tenant_id: str) -> None:
    """Wait until the firm's credentials can write its database, then create indexes.

    Args:
        uri: Firm connection string.
        tenant_id: Valid tenant id.

    Raises:
        RuntimeError: If access does not work before the timeout.
    """
    deadline = time.monotonic() + PROPAGATION_TIMEOUT_SECONDS
    db_name = tenant.database_name(tenant_id)
    while True:
        client: pymongo.MongoClient = pymongo.MongoClient(uri, serverSelectionTimeoutMS=10000)
        try:
            client[db_name]["audit"].insert_one({"event": "tenant.provisioned", "tenant_id": tenant_id})
            client[db_name]["carriers"].create_index("phone", unique=True)
            return
        except pymongo.errors.PyMongoError as exc:
            if time.monotonic() > deadline:
                raise RuntimeError(f"firm credentials cannot write {db_name}: {exc}") from exc
            time.sleep(PROPAGATION_POLL_SECONDS)
        finally:
            client.close()


def _lookup(node: object, dotted: str) -> object:
    """Walk a parsed YAML mapping by dotted path.

    Args:
        node: Parsed YAML document.
        dotted: Key path such as "plugins.isolation".

    Returns:
        The value, or None when absent.
    """
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def managed_value(dotted: str) -> object:
    """Read a key pinned by the administrator's managed config, if any.

    Args:
        dotted: Key path.

    Returns:
        The pinned value, or None when unpinned or no managed config exists.
    """
    if not MANAGED_CONFIG.is_file():
        return None
    return _lookup(YAML(typ="safe").load(MANAGED_CONFIG.read_text()) or {}, dotted)


def operator_config_value(dotted: str) -> object:
    """Read one value from the operator profile's config.yaml by dotted path.

    Args:
        dotted: Key path such as "model.default".

    Returns:
        The value, or None when absent.

    Raises:
        OSError: If config.yaml cannot be read.
    """
    return _lookup(YAML(typ="safe").load((HERMES_HOME / "config.yaml").read_text()) or {}, dotted)


def install_plugin(profile_dir: Path) -> None:
    """Copy this plugin into the profile's own plugins directory, replacing an older copy.

    Args:
        profile_dir: Firm profile directory.
    """
    target = profile_dir / "plugins" / PLUGIN_NAME
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(PLUGIN_DIR, target, ignore=PLUGIN_COPY_IGNORE)


def configure_profile(tenant_id: str, uri: str, dispatcher_phone: str) -> Path:
    """Create the Hermes profile and write its secrets, identity, and isolation config.

    Args:
        tenant_id: Valid tenant id.
        uri: Firm connection string.
        dispatcher_phone: Dispatcher's own number.

    Returns:
        The profile directory.
    """
    profile_dir = HERMES_HOME / "profiles" / tenant_id
    if not profile_dir.exists():
        hermes("profile", "create", tenant_id, "--description", f"AI dispatcher for firm {tenant_id}")
    operator_env = read_env(HERMES_HOME / ".env")
    secrets_out = {key: operator_env[key] for key in INHERITED_KEYS if operator_env.get(key)}
    secrets_out.update({tenant.TENANT_ENV: tenant_id, tenant.URI_ENV: uri,
                        "FREIGHT_DISPATCHER_PHONE": dispatcher_phone})
    upsert_env(profile_dir / ".env", secrets_out)
    (profile_dir / "SOUL.md").write_text((PLUGIN_DIR / "profile" / "SOUL.md").read_text())
    for key in INHERITED_CONFIG:
        value = operator_config_value(key)
        if value not in (None, "", []):
            hermes("-p", tenant_id, "config", "set", key, value if isinstance(value, str) else json.dumps(value))
    for key, value in ISOLATION_CONFIG.items():
        if managed_value(key) is None:
            hermes("-p", tenant_id, "config", "set", key, value)
    install_plugin(profile_dir)
    hermes("-p", tenant_id, "plugins", "enable", PLUGIN_NAME, "--no-allow-tool-override")
    return profile_dir


def provision(tenant_id: str, dispatcher_phone: str, shared_credentials: bool) -> Path:
    """Provision one firm end to end; safe to repeat for the same tenant.

    Args:
        tenant_id: Proposed tenant id.
        dispatcher_phone: Dispatcher's own number.
        shared_credentials: Reuse the operator's database user instead of a scoped one.

    Returns:
        The profile directory.

    Raises:
        tenant.TenantError: If the tenant id is invalid.
        RuntimeError: If the operator URI is missing or a provisioning step fails.
        OSError: If profile files cannot be written.
    """
    tenant_id = tenant.validate_tenant_id(tenant_id)
    base_uri = read_env(HERMES_HOME / ".env").get("MONGODB_URI") or os.environ.get("MONGODB_URI", "")
    if not base_uri:
        raise RuntimeError("operator MONGODB_URI not found in ~/.hermes/.env or the environment")
    if shared_credentials:
        print("warning: shared credentials; isolation is enforced by plugin code only", file=sys.stderr)
        uri = base_uri
    else:
        uri = with_credentials(base_uri, *create_scoped_user(tenant_id))
    wait_for_access(uri, tenant_id)
    return configure_profile(tenant_id, uri, dispatcher_phone)


def main() -> int:
    """Parse arguments and provision one firm.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(description="Provision a dispatch firm as an isolated Hermes tenant")
    parser.add_argument("tenant_id")
    parser.add_argument("--dispatcher-phone", required=True)
    parser.add_argument("--shared-credentials", action="store_true")
    args = parser.parse_args()
    tenant_id = args.tenant_id
    try:
        profile_dir = provision(tenant_id, args.dispatcher_phone, args.shared_credentials)
    except (RuntimeError, tenant.TenantError, OSError) as exc:
        print(f"provisioning failed: {exc}", file=sys.stderr)
        return 1
    print(f"provisioned {tenant_id}: profile {profile_dir}, database {tenant.database_name(tenant_id)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
