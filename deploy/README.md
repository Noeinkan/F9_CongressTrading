# VPS app deployment

Run the FastAPI + React app on a Linux VPS so it is reachable at a stable URL such as **http://77.42.70.26/** from any laptop.

Architecture:

- **congress-api** — uvicorn on `127.0.0.1:8000` (`python -m src.api`)
- **congress-web** — Caddy on port 80 serves `frontend/dist/` and reverse-proxies `/api/*` to the API

## Deploy latest `main` from your PC

Ensure `main` is pushed to GitHub (`git push origin main`), then from the repo root:

```bash
ssh root@77.42.70.26 'REPO_DIR=/opt/F9_CongressTrading bash -s' < deploy/deploy.sh
```

If the repo lives elsewhere on the VPS, set `REPO_DIR` to that path. The script runs `git pull`, installs Python requirements, builds the React frontend (`npm ci && npm run build`), and restarts `congress-api` and `congress-web` if systemd is installed.

### One-shot deploy (Windows)

From PowerShell at the repo root:

```powershell
.\deploy_local.ps1
```

It commits any pending changes (prompting for a message, or pass `-Message "..."`), pushes `main`, and pipes `deploy/deploy.sh` over SSH. Override the target with `-VpsUser`, `-VpsHost`, `-VpsRepoDir`.

One-liner without the script:

```bash
ssh root@77.42.70.26 'cd /opt/F9_CongressTrading && git pull --ff-only origin main && .venv/bin/pip install -q -r requirements.txt && cd frontend && npm ci && npm run build && sudo systemctl restart congress-api congress-web'
```

## Prerequisites

- Python 3.10+ venv at repo root (`.venv`)
- Node.js 20+ and `npm` (for the frontend build step)
- Caddy 2.x (`apt install caddy` or official install script)
- Ingested data under `data/db/` on the VPS
- `.env` with API keys and app settings (see repo `.env.example`)

## `.env` on the VPS

```bash
APP_USERNAME=admin
APP_PASSWORD=<long-random-secret>
APP_SESSION_SECRET=<optional-explicit-secret>
API_SERVER_ADDRESS=127.0.0.1
API_SERVER_PORT=8000
```

When `APP_PASSWORD` is set, the login page appears before any transaction data loads.

## Firewall

```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status
```

## Manual start (development-style)

```bash
cd /opt/F9_CongressTrading
source .venv/bin/activate
python -m src.api   # API on :8000

# separate terminal:
cd frontend && npm ci && npm run build && npm run preview  # or use Caddy in prod
```

Verify from another machine: open `http://<vps-public-ip>/` (Caddy on port 80).

## systemd

1. Edit `deploy/congress-api.service` and `deploy/congress-web.service`: set `User`, `WorkingDirectory`, `EnvironmentFile`, and `ExecStart` paths to match your install (defaults assume `/opt/F9_CongressTrading`).
2. Install the Caddy config:

```bash
sudo mkdir -p /etc/caddy/Caddyfile.d
sudo cp deploy/congress.caddy /etc/caddy/Caddyfile.d/congress.caddy
```

3. Install the units:

```bash
sudo cp deploy/congress-api.service /etc/systemd/system/
sudo cp deploy/congress-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now congress-api congress-web
sudo systemctl status congress-api congress-web
```

Logs: `journalctl -u congress-api -f` and `journalctl -u congress-web -f`

## Frontend rebuild

After code changes that touch the React app:

```bash
cd /opt/F9_CongressTrading/frontend
npm ci && npm run build
sudo systemctl reload congress-web
```

Caddy serves the updated `dist/` immediately on the next request.

## HTTPS (recommended later)

HTTP does not encrypt the login password on the network. When you have a domain, replace `:80` in `deploy/congress.caddy` with your domain name — Caddy obtains and renews Let's Encrypt certificates automatically:

```
yourdomain.com {
    root * /opt/F9_CongressTrading/frontend/dist
    encode gzip
    handle /api/* {
        reverse_proxy 127.0.0.1:8000
    }
    handle {
        try_files {path} /index.html
        file_server
    }
}
```

Set `APP_SESSION_HTTPS_ONLY=1` in `.env` so the session cookie is marked Secure.

## Security notes

| Control | Effect |
|---------|--------|
| Login gate (`APP_PASSWORD`) | Blocks casual access and crawlers |
| API on localhost only | FastAPI not exposed directly; Caddy is the public entry |
| HTTP | Password visible on the wire; prefer HTTPS for production |

Rotate `APP_PASSWORD` if the URL is shared widely.
