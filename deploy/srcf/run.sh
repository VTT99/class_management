#!/usr/bin/env bash
# Start uvicorn on a Unix socket. SRCF's Apache reverse-proxies to this
# socket via the .htaccess in deploy/srcf/htaccess-srcf.example.
#
# Run by the systemd user service at deploy/srcf/class-management.service.
# DO NOT invoke this directly to run the app long-term — let systemd manage
# it, so it restarts on crash and survives logout (with linger enabled).

set -euo pipefail

cd "$(dirname "$0")/../.."   # repo root

# Load .env so ROOT_PATH etc. are available.
if [ -f .env ]; then
    set -a; . ./.env; set +a
fi

# Create venv on first run.
if [ ! -d .venv ]; then
    python3 -m venv .venv
    .venv/bin/pip install --upgrade pip
    .venv/bin/pip install --prefer-binary -r requirements.txt
fi

SOCKET="${SRCF_UVICORN_SOCKET:-$PWD/web.sock}"

# Clean up any stale socket from a previous crash.
rm -f "$SOCKET"

exec .venv/bin/uvicorn app.main:app \
    --uds "$SOCKET" \
    --root-path "${ROOT_PATH:-}" \
    --proxy-headers --forwarded-allow-ips='*' \
    --log-level info
