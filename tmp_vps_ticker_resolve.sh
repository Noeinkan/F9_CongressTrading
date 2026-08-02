#!/usr/bin/env bash
set -euo pipefail
REPO_DIR="${REPO_DIR:-/opt/F9_CongressTrading}"
cd "$REPO_DIR"

echo "== git =="
git rev-parse --short HEAD
git log -1 --oneline

echo "== API keys present? =="
.venv/bin/python - <<'PY'
import os
from pathlib import Path
# load .env the same way the app does
env_path = Path(".env")
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v
poly = bool((os.getenv("POLYGON_API_KEY") or "").strip())
figi = bool((os.getenv("OPENFIGI_API_KEY") or "").strip())
print(f"POLYGON_API_KEY set={poly}")
print(f"OPENFIGI_API_KEY set={figi}")
if not poly and not figi:
    raise SystemExit("Need POLYGON_API_KEY or OPENFIGI_API_KEY on the VPS")
PY

echo "== empty ticker counts BEFORE =="
.venv/bin/python - <<'PY'
import sqlite3
c = sqlite3.connect("data/db/congress_trades.sqlite")
total = c.execute("select count(*) from transactions").fetchone()[0]
empty = c.execute(
    "select count(*) from transactions where coalesce(trim(ticker),'')=''"
).fetchone()[0]
filled = total - empty
print(f"total={total} filled={filled} empty={empty}")
PY

echo "== re-resolve empty tickers =="
.venv/bin/python scripts/re_resolve_empty_tickers.py

echo "== empty ticker counts AFTER =="
.venv/bin/python - <<'PY'
import sqlite3
c = sqlite3.connect("data/db/congress_trades.sqlite")
total = c.execute("select count(*) from transactions").fetchone()[0]
empty = c.execute(
    "select count(*) from transactions where coalesce(trim(ticker),'')=''"
).fetchone()[0]
filled = total - empty
print(f"total={total} filled={filled} empty={empty}")
PY

echo "== ensure frontend build matches HEAD (TickerLink etc) =="
# Rebuild if dist is older than the commit tree for frontend ticker links
if [ ! -f frontend/dist/index.html ] || [ frontend/src/components/TickerLink.tsx -nt frontend/dist/index.html ]; then
  echo "Rebuilding frontend..."
  (cd frontend && npm ci --silent && npm run build)
else
  echo "frontend/dist looks current; skip rebuild"
fi

echo "== restart API =="
if systemctl is-active --quiet congress-api; then
  systemctl restart congress-api
  sleep 1
  systemctl is-active congress-api
else
  echo "congress-api not active"
fi
if systemctl is-active --quiet congress-web; then
  systemctl restart congress-web
  systemctl is-active congress-web
fi

echo "DONE"
