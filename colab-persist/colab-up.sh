#!/usr/bin/env bash
# Run on the Mac: push persistence scripts and secrets to a Colab VM, then rebuild
# Hermes there in the background.
#   colab-persist/colab-up.sh [SESSION_NAME]
# Secrets are read from atlas-credentials.env (MONGODB_URI) and hermes-secrets.env
# (ANTHROPIC_API_KEY, DEEPSEEK_API_KEY) next to this folder and sent over SSH stdin.
set -euo pipefail

SESSION="${1:-hermes}"
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$HERE")"
ATLAS_FILE="$ROOT/atlas-credentials.env"
SECRETS_FILE="$ROOT/hermes-secrets.env"
REMOTE_DIR="/opt/hermes-persist"
SECRET_KEYS=(ANTHROPIC_API_KEY DEEPSEEK_API_KEY)

vm() {
    ssh -o ProxyCommand="colab ssh --proxy-mode -s %h" -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -o ServerAliveInterval=30 \
        "root@$SESSION" "$@" 2> >(grep -v '^\[colab\]' >&2)
}

read_key() {
    # Print KEY's value from an env file with surrounding quotes removed.
    grep -E "^$1=" "$2" 2>/dev/null | tail -1 | cut -d= -f2- | sed -E "s/^[\"'](.*)[\"']$/\1/"
}

[ -f "$ATLAS_FILE" ] || { echo "missing $ATLAS_FILE" >&2; exit 1; }
uri="$(read_key MONGODB_URI "$ATLAS_FILE")"
[ -n "$uri" ] || { echo "MONGODB_URI missing from $ATLAS_FILE" >&2; exit 1; }

secrets="MONGODB_URI='$uri'"$'\n'
for key in "${SECRET_KEYS[@]}"; do
    value="$(read_key "$key" "$SECRETS_FILE")"
    if [ -n "$value" ]; then
        secrets+="$key='$value'"$'\n'
    else
        echo "warning: $key not set in $SECRETS_FILE" >&2
    fi
done

vm "mkdir -p $REMOTE_DIR && chmod 700 $REMOTE_DIR"
vm "cat > $REMOTE_DIR/hermes_persist.py" <"$HERE/hermes_persist.py"
vm "cat > $REMOTE_DIR/rebuild.sh && chmod +x $REMOTE_DIR/rebuild.sh" <"$HERE/rebuild.sh"
printf '%s' "$secrets" | vm "umask 077 && cat > $REMOTE_DIR/secrets.env"

vm "nohup bash $REMOTE_DIR/rebuild.sh > /var/log/hermes-rebuild.log 2>&1 &"
echo "Rebuild started on $SESSION. Follow it with:"
echo "  ssh -o ProxyCommand=\"colab ssh --proxy-mode -s %h\" root@$SESSION tail -f /var/log/hermes-rebuild.log"
