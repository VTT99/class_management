#!/usr/bin/env bash
# Start (or restart) the FastAPI backend in the background via nohup.
#
# Usage:   ./deploy/start.sh
# Logs:    ./uvicorn.log
# PID:     ./.uvicorn.pid

set -euo pipefail

# Run from the repo root regardless of where the script is called from.
cd "$(dirname "$0")/.."

VENV=.venv
PIDFILE=.uvicorn.pid
LOG=uvicorn.log
HOST=127.0.0.1
PORT=8000

# Load .env so ROOT_PATH etc. are available to uvicorn.
if [ -f .env ]; then
    set -a; . ./.env; set +a
fi

# Make sure the venv exists.
if [ ! -d "$VENV" ]; then
    echo "Creating virtualenv in $VENV ..."
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install --quiet -r requirements.txt
fi

# Kill any previous instance.
if [ -f "$PIDFILE" ]; then
    OLD_PID=$(cat "$PIDFILE" || true)
    if [ -n "${OLD_PID:-}" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        echo "Stopping previous uvicorn (pid=$OLD_PID) ..."
        kill "$OLD_PID" || true
        sleep 1
    fi
    rm -f "$PIDFILE"
fi

# Launch.
nohup "$VENV/bin/uvicorn" app.main:app \
    --host "$HOST" --port "$PORT" \
    --root-path "${ROOT_PATH:-}" \
    --proxy-headers --forwarded-allow-ips=127.0.0.1 \
    > "$LOG" 2>&1 &

NEW_PID=$!
echo "$NEW_PID" > "$PIDFILE"
sleep 1

if kill -0 "$NEW_PID" 2>/dev/null; then
    echo "Started uvicorn pid=$NEW_PID on $HOST:$PORT (logs: $LOG)"
else
    echo "FAILED to start uvicorn. Last log lines:" >&2
    tail -n 30 "$LOG" >&2
    rm -f "$PIDFILE"
    exit 1
fi
