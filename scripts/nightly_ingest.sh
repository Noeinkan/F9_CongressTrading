#!/usr/bin/env bash
# Nightly data ingest + CSV export for the Congress Trading dashboard.
# Triggered by /etc/cron.d/f9-congress-trading.
#
# Why not `python -m src.main refresh-dashboard`?
#   refresh-dashboard kills the listening process and respawns it. That fights
#   with the systemd unit (Restart=on-failure). This script just updates the
#   data + CSVs that the dashboard reads; systemd keeps managing the process.
#
# Why flock?
#   Cheap insurance against overlap if a run stalls past the next night's fire.
#   Lock is held for the duration of the script; second run exits 0 immediately.
#
# Why set -euo pipefail?
#   Any failed step aborts the rest, so a broken ingest does not silently leave
#   half-updated CSVs. Final "done" line in the log proves it ran to completion.

set -euo pipefail
umask 077

REPO="/opt/F9_CongressTrading"
LOG_DIR="/var/log/f9-congress-trading"
LOG="${LOG_DIR}/ingest.log"
LOCK="/var/lock/f9-congress-trading-ingest.lock"

mkdir -p "$LOG_DIR"
# Open the lock FD once and keep it for the whole script. flock -n fails (rc=1)
# if another process already holds the lock, so we exit 0 in that case.
exec 9>>"$LOCK"
if ! flock -n 9; then
  echo "[$(date -Iseconds)] another ingest is already running; exiting" >> "$LOG"
  exit 0
fi

{
  echo "================================================================"
  echo "[$(date -Iseconds)] nightly ingest starting (pid=$$)"
  echo "HEAD: $(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo unknown)"
  cd "$REPO"

  echo "--- ingest-all ---"
  ./.venv/bin/python -m src.main ingest-all

  echo "--- export-csv ---"
  ./.venv/bin/python -m src.main export-csv
  echo "--- export-fd-csv ---"
  ./.venv/bin/python -m src.main export-fd-csv
  echo "--- export-review-csv ---"
  ./.venv/bin/python -m src.main export-review-csv

  echo "[$(date -Iseconds)] nightly ingest done (rc=0)"
} >> "$LOG" 2>&1
