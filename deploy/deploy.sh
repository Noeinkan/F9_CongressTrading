#!/usr/bin/env bash
# Deploy latest main on the VPS. Run on the server as root or a user with repo access.
set -euo pipefail

REPO_DIR="${REPO_DIR:-/opt/F9_CongressTrading}"
API_SERVICE="${API_SERVICE:-congress-api}"
WEB_SERVICE="${WEB_SERVICE:-congress-web}"

cd "$REPO_DIR"

if [[ ! -d .git ]]; then
  echo "Not a git repo: $REPO_DIR" >&2
  exit 1
fi

git fetch origin
# --autostash stashes any local modifications (e.g. from a hook or stray edit),
# pulls, then pops the stash. If the pop conflicts, the stash is preserved and
# the operator can resolve it. This avoids the "Your local changes would be
# overwritten by merge" abort on a fast-forward pull.
git pull --ff-only --autostash origin main
git stash list || true

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi

.venv/bin/pip install -q -r requirements.txt

if command -v npm >/dev/null 2>&1; then
  pushd frontend >/dev/null
  npm ci
  npm run build
  popd >/dev/null
else
  echo "npm not found — skipping frontend build (install Node.js 20+ on the VPS)" >&2
fi

if systemctl is-active --quiet "$API_SERVICE" 2>/dev/null; then
  systemctl restart "$API_SERVICE"
  echo "Restarted $API_SERVICE"
  systemctl --no-pager status "$API_SERVICE" | head -12
else
  echo "Service $API_SERVICE not installed; start manually:"
  echo "  cd $REPO_DIR && .venv/bin/python -m src.api"
fi

if systemctl is-active --quiet "$WEB_SERVICE" 2>/dev/null; then
  systemctl restart "$WEB_SERVICE"
  echo "Restarted $WEB_SERVICE"
  systemctl --no-pager status "$WEB_SERVICE" | head -12
else
  echo "Service $WEB_SERVICE not installed; install Caddy and deploy/congress.caddy first."
fi

echo "Deployed: $(git rev-parse --short HEAD)"
