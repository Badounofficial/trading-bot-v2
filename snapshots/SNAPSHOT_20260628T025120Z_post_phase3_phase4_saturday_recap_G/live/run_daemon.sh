#!/usr/bin/env bash
# run_daemon.sh — Sleep-immune, auto-restart wrapper for paper_funding_capture.py
#
# Behaviour:
#   - `caffeinate -i` prevents the Mac from idle-sleeping (display can still sleep)
#   - Auto-restarts the daemon if it crashes (loop with exponential backoff)
#   - All stdout/stderr piped to a daily log file
#   - Exit code 0 only if asked to stop via SIGTERM/SIGINT
#
# Usage:
#   bash live/run_daemon.sh           # launches the daemon in this terminal
#   nohup bash live/run_daemon.sh &   # launches detached, survives terminal close
#
# Stop:
#   - From the same machine: `pkill -f paper_funding_capture` or `Ctrl-C` in the terminal
#   - From iPhone via SSH: ssh badoun@<mac-hostname> 'pkill -f paper_funding_capture'

set -uo pipefail

# Resolve project root regardless of where this script is called from
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

LOG_DIR="$PROJECT_ROOT/live/logs"
mkdir -p "$LOG_DIR"

PY="${PYTHON:-python3}"
BACKOFF=5            # seconds, doubles on each crash up to MAX_BACKOFF
MAX_BACKOFF=300
RESTART_COUNT=0

# Forward SIGTERM/SIGINT to the child so the daemon shuts down cleanly
trap 'echo "[wrapper] caught signal — stopping"; kill -TERM "$child_pid" 2>/dev/null; wait "$child_pid" 2>/dev/null; exit 0' SIGTERM SIGINT

echo "[wrapper] starting paper_funding_capture daemon (PID wrapper=$$)"
echo "[wrapper] log dir: $LOG_DIR"

while true; do
  LOG_FILE="$LOG_DIR/wrapper_$(date -u +%Y-%m-%d).log"
  echo "[wrapper $(date -u +%H:%M:%SZ)] launching daemon (restart #$RESTART_COUNT, backoff=${BACKOFF}s)" \
       | tee -a "$LOG_FILE"

  # caffeinate -i: prevent idle sleep. -s would also prevent system sleep but
  # requires Mac to be plugged in. -i is enough for our purpose (Mac stays running).
  caffeinate -i "$PY" "$PROJECT_ROOT/live/paper_funding_capture.py" 2>&1 | tee -a "$LOG_FILE" &
  child_pid=$!
  wait "$child_pid"
  exit_code=$?

  echo "[wrapper $(date -u +%H:%M:%SZ)] daemon exited with code $exit_code" | tee -a "$LOG_FILE"

  if [ "$exit_code" -eq 0 ]; then
    # Clean shutdown via signal
    echo "[wrapper] clean exit, stopping wrapper" | tee -a "$LOG_FILE"
    break
  fi

  RESTART_COUNT=$((RESTART_COUNT + 1))
  echo "[wrapper] crash detected, restarting in ${BACKOFF}s …" | tee -a "$LOG_FILE"
  sleep "$BACKOFF"
  BACKOFF=$((BACKOFF * 2))
  [ "$BACKOFF" -gt "$MAX_BACKOFF" ] && BACKOFF="$MAX_BACKOFF"
done

echo "[wrapper] done."
