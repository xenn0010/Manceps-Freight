#!/usr/bin/env bash
# Bring Hermes back on a fresh Colab VM: pinned install, Atlas snapshot restore,
# secrets, backup loop, and the gateway when ~/.hermes/.autostart-gateway exists.
# Pushed and started by colab-up.sh on the Mac; expects $SECRETS_FILE on the VM.
set -euo pipefail

HERMES_COMMIT="${HERMES_COMMIT:-1c0cd66774}"
HERMES_REPO="https://github.com/NousResearch/hermes-agent.git"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
SRC_DIR="$HERMES_HOME/hermes-agent"
PERSIST_DIR="/opt/hermes-persist"
PERSIST="$PERSIST_DIR/hermes_persist.py"
SECRETS_FILE="$PERSIST_DIR/secrets.env"
WORK_DIR="/content/work"
BACKUP_INTERVAL_SECONDS="${BACKUP_INTERVAL_SECONDS:-300}"
BACKUP_LOG="/var/log/hermes-persist.log"
INSTALL_LOG="/var/log/hermes-install.log"
GATEWAY_LOG="/var/log/hermes-gateway.log"
PYMONGO_SPEC="pymongo>=4.10,<5"
MODEL_KEYS=(ANTHROPIC_API_KEY DEEPSEEK_API_KEY)

[ -f "$SECRETS_FILE" ] || { echo "missing $SECRETS_FILE" >&2; exit 1; }
set -a
# shellcheck source=/dev/null
. "$SECRETS_FILE"
set +a
[ -n "${MONGODB_URI:-}" ] || { echo "MONGODB_URI missing from $SECRETS_FILE" >&2; exit 1; }

python3 -c "import pymongo" 2>/dev/null || python3 -m pip install -q "$PYMONGO_SPEC"
export PATH="$HOME/.local/bin:$PATH"

if ! command -v hermes >/dev/null; then
    mkdir -p "$HERMES_HOME"
    [ -d "$SRC_DIR/.git" ] || git clone -q "$HERMES_REPO" "$SRC_DIR"
    git -C "$SRC_DIR" checkout -q "$HERMES_COMMIT"
    echo "Installing Hermes $HERMES_COMMIT (log: $INSTALL_LOG)"
    if ! bash "$SRC_DIR/scripts/install.sh" --dir "$SRC_DIR" --commit "$HERMES_COMMIT" \
            --non-interactive --verbose >"$INSTALL_LOG" 2>&1; then
        tail -40 "$INSTALL_LOG" >&2
        exit 1
    fi
fi

mkdir -p "$WORK_DIR"
python3 "$PERSIST" restore

# Model keys live in Hermes's own .env; upsert them without echoing values.
ENV_FILE="$HERMES_HOME/.env" python3 - "${MODEL_KEYS[@]}" <<'PY'
import os, sys
from pathlib import Path
env_file = Path(os.environ["ENV_FILE"])
lines = env_file.read_text().splitlines() if env_file.exists() else []
for key in sys.argv[1:]:
    value = os.environ.get(key)
    if not value:
        continue
    lines = [l for l in lines if not l.startswith(f"{key}=")] + [f"{key}={value}"]
env_file.write_text("\n".join(lines) + "\n")
env_file.chmod(0o600)
PY

if ! pgrep -f "hermes_persist.py loop" >/dev/null; then
    nohup python3 "$PERSIST" loop --interval "$BACKUP_INTERVAL_SECONDS" >>"$BACKUP_LOG" 2>&1 &
    echo "Backup loop started every ${BACKUP_INTERVAL_SECONDS}s (log: $BACKUP_LOG)"
fi

hermes --version

if [ -f "$HERMES_HOME/.autostart-gateway" ] && ! pgrep -f "hermes gateway run" >/dev/null; then
    nohup hermes gateway run >>"$GATEWAY_LOG" 2>&1 &
    echo "Gateway started (log: $GATEWAY_LOG)"
fi
echo "rebuild complete"
