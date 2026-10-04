#!/usr/bin/env bash
# Start the API in the background for local checks.
#   scripts/serve_backend.sh [port] [logfile]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${1:-8000}"
LOGFILE="${2:-/tmp/rain_corrector_api.log}"
PIDFILE="/tmp/rain_corrector_api.pid"

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "already running (pid $(cat "$PIDFILE"))"
  exit 0
fi

cd "$REPO_ROOT/backend"
setsid .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port "$PORT" \
  > "$LOGFILE" 2>&1 < /dev/null &
echo $! > "$PIDFILE"

for _ in $(seq 1 30); do
  if curl -fsS --max-time 2 "http://localhost:$PORT/api/v1/health" >/dev/null 2>&1; then
    echo "api ready on http://localhost:$PORT (pid $(cat "$PIDFILE"), log $LOGFILE)"
    exit 0
  fi
  sleep 1
done

echo "api did not become ready; see $LOGFILE" >&2
exit 1
