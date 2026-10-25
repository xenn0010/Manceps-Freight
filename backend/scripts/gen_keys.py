"""Print a new Ed25519 JWT signing key pair and a SECRETS_KEY as JSON on stdout (nothing is written to disk).

Usage (working directory backend/):
    uv run python scripts/gen_keys.py
Copy the values into the deployment's secret store as JWT_ACTIVE_KID, JWT_KEYS_JSON and SECRETS_KEY.
"""

from __future__ import annotations

import base64
import json
import secrets
import sys
from datetime import UTC, datetime

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

SECRETS_KEY_BYTES = 32
KID_SUFFIX_BYTES = 4
EXIT_OK = 0


def new_kid() -> str:
    """Make a key id that sorts by creation date.

    Returns:
        Id like "k20261025-1a2b3c4d".
    """
    return f"k{datetime.now(UTC):%Y%m%d}-{secrets.token_hex(KID_SUFFIX_BYTES)}"


def generate() -> dict[str, str]:
    """Generate the key material.

    Returns:
        Environment variable name to value.
    """
    private = Ed25519PrivateKey.generate()
    private_pem = private.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()).decode("ascii")
    public_pem = private.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo).decode("ascii")
    kid = new_kid()
    keys = {kid: {"private_pem": private_pem, "public_pem": public_pem}}
    return {
        "JWT_ACTIVE_KID": kid,
        "JWT_KEYS_JSON": json.dumps(keys, separators=(",", ":")),
        "SECRETS_KEY": base64.urlsafe_b64encode(secrets.token_bytes(SECRETS_KEY_BYTES)).decode("ascii"),
    }


def main() -> int:
    """Print fresh key material.

    Returns:
        0.
    """
    print(json.dumps(generate(), indent=2))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
