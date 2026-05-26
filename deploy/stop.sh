#!/usr/bin/env bash
# Stop the FastAPI backend started by deploy/start.sh.
#
# Usage:   ./deploy/stop.sh

set -euo pipefail

cd "$(dirname "$0")/.."

PIDFILE=.uvicorn.pid

if [ ! -f "$PIDFILE" ]; then
    echo "No pidfile at $PIDFILE; nothing to stop."
    exit 0
fi

PID=$(cat "$PIDFILE")
if kill -0 "$PID" 2>/dev/null; then
    kill "$PID"
    echo "Stopped uvicorn (pid=$PID)."
else
    echo "Process $PID is not running."
fi
rm -f "$PIDFILE"
