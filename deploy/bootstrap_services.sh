#!/usr/bin/env bash
# bootstrap_services.sh - One-time install of Caddy + systemd units on the VPS.
# Idempotent: re-running on an already-installed box is a no-op.
#
# Run from the repo root on the VPS:
#   cd /opt/F9_CongressTrading
#   sudo bash deploy/bootstrap_services.sh
#
# After this, the FastAPI service runs under systemd (no more screen/tmux)
# and Caddy serves the React build on http://77.42.70.26/.
set -euo pipefail

REPO_DIR="${REPO_DIR:-/opt/F9_CongressTrading}"

if [[ ! -d "$REPO_DIR/.git" ]]; then
  echo "Repo not found at $REPO_DIR" >&2
  exit 1
fi

# 1. Install Caddy (official repo so version is current).
if ! command -v caddy >/dev/null 2>&1; then
  echo "Installing Caddy..."
  apt-get update -qq
  apt-get install -y -qq debian-keyring debian-archive-keyring apt-transport-https curl
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    | tee /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -qq
  apt-get install -y -qq caddy
else
  echo "Caddy already installed: $(caddy version)"
fi

# 2. Make sure the unprivileged 'deploy' user exists (matches the systemd units).
if ! id deploy >/dev/null 2>&1; then
  useradd --system --create-home --shell /usr/sbin/nologin deploy
fi

# 3. Hand the repo + venv to 'deploy' so the service can read everything.
chown -R deploy:deploy "$REPO_DIR"

# 4. Caddy config.
install -d /etc/caddy/Caddyfile.d
install -m 0644 "$REPO_DIR/deploy/congress.caddy" /etc/caddy/Caddyfile.d/congress.caddy
# Drop the Caddyfile's main include of the snippet so /etc/caddy/Caddyfile
# delegates to our snippet. This is a no-op if already present.
if [[ -f /etc/caddy/Caddyfile ]] && ! grep -q 'Caddyfile.d' /etc/caddy/Caddyfile; then
  echo 'import /etc/caddy/Caddyfile.d/*.caddy' > /etc/caddy/Caddyfile.import
  printf '\n%s\n' 'import /etc/caddy/Caddyfile.d/*.caddy' >> /etc/caddy/Caddyfile
fi

# 5. systemd units.
install -m 0644 "$REPO_DIR/deploy/congress-api.service" /etc/systemd/system/congress-api.service
install -m 0644 "$REPO_DIR/deploy/congress-web.service" /etc/systemd/system/congress-web.service
systemctl daemon-reload
systemctl enable --now congress-api.service
systemctl enable --now congress-web.service
systemctl restart caddy 2>/dev/null || systemctl start caddy || true

# 6. Open the firewall if ufw is in use.
if command -v ufw >/dev/null 2>&1; then
  ufw allow 80/tcp  || true
  ufw allow 443/tcp || true
fi

echo
echo "=== status ==="
systemctl --no-pager status congress-api  | head -12 || true
systemctl --no-pager status congress-web  | head -12 || true
ss -ltn | awk 'NR==1 || $4 ~ /:(80|443|8000)$/'
echo
echo "Smoke tests:"
curl -sS -o /dev/null -w "  http 80  -> %{http_code}\n" --max-time 5 http://127.0.0.1/
curl -sS -o /dev/null -w "  api 8000 -> %{http_code}\n" --max-time 5 http://127.0.0.1:8000/api/health
echo
echo "Done. Dashboard: http://77.42.70.26/"
