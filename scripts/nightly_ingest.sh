#!/usr/bin/env bash
# Nightly data ingest + CSV export + Telegram notifications for the Congress
# Trading dashboard. Triggered by /etc/cron.d/f9-congress-trading, installed
# from deploy/f9-congress-trading.cron. The sidebar Refresh button runs the same
# steps from the API (src/post_ingest.py), sending the digest on any weekday
# unless one went out in the last 12 hours.
#
# This script updates the data + CSVs that the API reads and then reports what
# arrived; the congress-api systemd unit keeps managing the process
# independently.
#
# Why flock?
#   Cheap insurance against overlap if a run stalls past the next night's fire.
#   Lock is held for the duration of the script; second run exits 0 immediately.
#
# Why set -euo pipefail?
#   Any failed step aborts the rest, so a broken ingest does not silently leave
#   half-updated CSVs. Final "done" line in the log proves it ran to completion.
#
# Why an ERR trap?
#   A crashed ingest used to be visible only to whoever opened the log. The trap
#   sends one Telegram message naming the failing line, which is the difference
#   between noticing tonight and noticing in three weeks.
#
# Why both notify commands every night?
#   notify-events is silent unless something notable landed, and notify-digest
#   self-gates to CONGRESS_NOTIFY_DIGEST_WEEKDAY (Monday by default). One cron
#   entry therefore covers both the instant alerts and the weekly roundup.

set -euo pipefail
umask 077

REPO="/opt/F9_CongressTrading"
PYTHON="${REPO}/.venv/bin/python"
LOG_DIR="/var/log/f9-congress-trading"
LOG="${LOG_DIR}/ingest.log"
LOCK="/var/lock/f9-congress-trading-ingest.lock"

mkdir -p "$LOG_DIR"

on_error() {
  local rc=$?
  local line="${1:-unknown}"
  {
    echo "[$(date -Iseconds)] FAILED at line ${line} (rc=${rc})"
    # Best-effort alert. It must never turn a data failure into a shell error,
    # hence the `|| true`: if Telegram is also down, the log line above stands.
    cd "$REPO" 2>/dev/null && "$PYTHON" -m src.main notify-failure \
      --message "Nightly ingest failed at line ${line} (rc=${rc}). Log: ${LOG}" || true
  } >> "$LOG" 2>&1
  exit "$rc"
}
trap 'on_error $LINENO' ERR

# Open the lock FD once and keep it for the whole script. flock -n fails (rc=1)
# if another process already holds the lock, so we exit 0 in that case.
exec 9>>"$LOCK"
if ! flock -n 9; then
  echo "[$(date -Iseconds)] another ingest is already running; exiting" >> "$LOG"
  exit 0
fi

notify_rc=0

{
  echo "================================================================"
  echo "[$(date -Iseconds)] nightly ingest starting (pid=$$)"
  echo "HEAD: $(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo unknown)"
  cd "$REPO"

  # ingest-all reads the House Clerk's yearly index but never re-downloads it,
  # so without this step the House side froze at whatever index was on disk
  # (12-16 Sep 2026: four nights, six filings missed). --refresh re-fetches the
  # current year, exactly as the sidebar Refresh button does.
  echo "--- download-house-fd ---"
  "$PYTHON" -m src.main download-house-fd --refresh

  echo "--- ingest-all ---"
  "$PYTHON" -m src.main ingest-all

  echo "--- export-csv ---"
  "$PYTHON" -m src.main export-csv
  echo "--- export-fd-csv ---"
  "$PYTHON" -m src.main export-fd-csv
  echo "--- export-review-csv ---"
  "$PYTHON" -m src.main export-review-csv

  # Notifications run after the data is on disk, and their failures are
  # collected rather than fatal: the ingest already succeeded, and a Telegram
  # outage must not make the night look like a data failure. The non-zero exit
  # at the end is what surfaces it to cron.
  echo "--- notify-events ---"
  "$PYTHON" -m src.main notify-events || notify_rc=$?
  echo "--- notify-digest ---"
  "$PYTHON" -m src.main notify-digest || notify_rc=$?

  if [ "$notify_rc" -ne 0 ]; then
    echo "[$(date -Iseconds)] nightly ingest done, NOTIFICATIONS FAILED (rc=${notify_rc})"
  else
    echo "[$(date -Iseconds)] nightly ingest done (rc=0)"
  fi
} >> "$LOG" 2>&1

exit "$notify_rc"
