#!/usr/bin/env bash
# deploy.sh - One-shot deploy of the F9_CongressTrading stack on the VPS.
# Idempotent: re-running on an already-deployed box is safe.
#
# What it does:
#   1. git pull --ff-only (refuses to merge/rebase; manual intervention required otherwise)
#   2. pip install -r requirements.txt into the project venv
#   3. npm ci && npm run build for the React frontend
#   4. Restart congress-api + congress-web via systemctl (only if systemd is available)
#
# Run from the repo root on the VPS:
#   bash deploy.sh
#
# Override the repo location:
#   REPO_DIR=/srv/F9_CongressTrading bash deploy.sh
#
# Skip the frontend rebuild (faster, e.g. backend-only change):
#   SKIP_FRONTEND=1 bash deploy.sh
#
# Skip the service restart (e.g. you're restarting by hand):
#   SKIP_RESTART=1 bash deploy.sh
set -euo pipefail

REPO_DIR="${REPO_DIR:-/opt/F9_CongressTrading}"

if [[ ! -d "$REPO_DIR/.git" ]]; then
  echo "Repo not found at $REPO_DIR (no .git directory)." >&2
  echo "Override with: REPO_DIR=/path/to/repo bash deploy.sh" >&2
  exit 1
fi

cd "$REPO_DIR"

echo "=== git pull (ff-only) ==="
if ! git pull --ff-only origin "${BRANCH:-main}"; then
  echo "git pull --ff-only failed." >&2
  echo "Likely local commits or non-ff remote history on '$REPO_DIR'." >&2
  echo "Inspect with 'git status' and resolve manually, then rerun." >&2
  exit 1
fi

echo "=== python deps ==="
if [[ ! -x ".venv/bin/python" ]]; then
  echo "Missing venv at $REPO_DIR/.venv. Create it first:" >&2
  echo "  python3 -m venv .venv && .venv/bin/pip install -U pip" >&2
  exit 1
fi
.venv/bin/pip install -q -r requirements.txt

if [[ "${SKIP_FRONTEND:-0}" != "1" ]]; then
  echo "=== frontend build ==="
  if [[ ! -d frontend ]]; then
    echo "Missing frontend/ directory in $REPO_DIR." >&2
    exit 1
  fi
  pushd frontend >/dev/null
  if [[ ! -d node_modules ]]; then
    npm ci
  else
    npm ci
  fi
  npm run build
  popd >/dev/null
else
  echo "=== frontend build: SKIPPED (SKIP_FRONTEND=1) ==="
fi

if [[ "${SKIP_RESTART:-0}" != "1" ]]; then
  echo "=== restart services ==="
  if command -v systemctl >/dev/null 2>&1 && systemctl --no-pager list-unit-files congress-api.service >/dev/null 2>&1; then
    sudo systemctl restart congress-api congress-web
    echo "Restarted congress-api + congress-web."
  else
    echo "systemd / congress-api.service not present; skipping service restart." >&2
    echo "Restart your API and Caddy by hand (see deploy/README.md)." >&2
  fi
else
  echo "=== restart services: SKIPPED (SKIP_RESTART=1) ==="
fi

echo
echo "=== status ==="
if command -v systemctl >/dev/null 2>&1; then
  systemctl --no-pager status congress-api | head -12 || true
  systemctl --no-pager status congress-web | head -12 || true
fi
echo
echo "Smoke tests:"
curl -sS -o /dev/null -w "  http 80  -> %{http_code}\n" --max-time 5 http://127.0.0.1/ || true
curl -sS -o /dev/null -w "  api 9001 -> %{http_code}\n" --max-time 5 http://127.0.0.1:9001/api/health || true

echo
echo "Deploy complete."