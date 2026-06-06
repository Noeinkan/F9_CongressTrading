#!/usr/bin/env bash
# Deploy latest main on the VPS. Run on the server as root or a user with repo access.
set -euo pipefail

REPO_DIR="${REPO_DIR:-/opt/F9_CongressTrading}"
SERVICE_NAME="${SERVICE_NAME:-congress-dashboard}"

cd "$REPO_DIR"

if [[ ! -d .git ]]; then
  echo "Not a git repo: $REPO_DIR" >&2
  exit 1
fi

git fetch origin
git pull --ff-only origin main

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi

.venv/bin/pip install -q -r requirements.txt

if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
  systemctl restart "$SERVICE_NAME"
  echo "Restarted $SERVICE_NAME"
  systemctl --no-pager status "$SERVICE_NAME" | head -12
else
  echo "Service $SERVICE_NAME not installed; start manually:"
  echo "  cd $REPO_DIR && .venv/bin/python -m src.main dashboard"
fi

echo "Deployed: $(git rev-parse --short HEAD)"
