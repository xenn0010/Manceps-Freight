#!/usr/bin/env bash
# Open an interactive shell on the Colab VM with hermes on PATH.
#   colab-persist/hermes-shell.sh [SESSION_NAME]
set -euo pipefail

SESSION="${1:-hermes}"

exec ssh -t -o ProxyCommand="colab ssh --proxy-mode -s %h" -o StrictHostKeyChecking=no \
    -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -o ServerAliveInterval=30 \
    "root@$SESSION" 'export PATH="$HOME/.local/bin:$PATH"; cd /root;
if grep -q INSTALL_EXIT=0 /var/log/hermes-install.log 2>/dev/null; then
    echo "Hermes is installed. Start it with: hermes"
else
    echo "Hermes is still installing. Watch it with: tail -f /var/log/hermes-install.log"
    echo "When it prints INSTALL_EXIT=0, run: source ~/.bashrc && hermes"
fi
exec bash -l'
