# VPS dashboard deployment

Run the Streamlit dashboard on a Linux VPS so it is reachable at a stable URL such as **http://77.42.70.26:8501/** from any laptop.

## Deploy latest `main` from your PC

Ensure `main` is pushed to GitHub (`git push origin main`), then from the repo root:

```bash
ssh root@77.42.70.26 'REPO_DIR=/opt/F9_CongressTrading bash -s' < deploy/deploy.sh
```

If the repo lives elsewhere on the VPS, set `REPO_DIR` to that path. The script runs `git pull`, installs requirements, and restarts `congress-dashboard` if systemd is installed.

### One-shot deploy (Windows)

From PowerShell at the repo root:

```powershell
.\deploy_local.ps1
```

It commits any pending changes (prompting for a message, or pass `-Message "..."`), pushes `main`, and pipes `deploy/deploy.sh` over SSH. Override the target with `-VpsUser`, `-VpsHost`, `-VpsRepoDir`.

One-liner without the script:

```bash
ssh root@77.42.70.26 'cd /opt/F9_CongressTrading && git pull --ff-only origin main && .venv/bin/pip install -q -r requirements.txt && sudo systemctl restart congress-dashboard'
```

## Prerequisites

- Python 3.10+ venv at repo root (`.venv`)
- Ingested data under `data/db/` on the VPS
- `.env` with API keys and dashboard settings (see repo `.env.example`)

## `.env` on the VPS

```bash
DASHBOARD_SERVER_ADDRESS=0.0.0.0
DASHBOARD_SERVER_PORT=8501
DASHBOARD_USERNAME=admin
DASHBOARD_PASSWORD=<long-random-secret>
```

When `DASHBOARD_PASSWORD` is set, the app shows a login form before loading any transaction data.

## Firewall

```bash
sudo ufw allow 8501/tcp
sudo ufw enable
sudo ufw status
```

## Manual start

```bash
cd /opt/F9_CongressTrading
source .venv/bin/activate
python -m src.main dashboard
```

Verify from another machine: open `http://<vps-public-ip>:8501/` (one colon before the port).

## systemd

1. Edit `deploy/congress-dashboard.service`: set `User`, `WorkingDirectory`, `EnvironmentFile`, and `ExecStart` paths to match your install (defaults assume `/opt/F9_CongressTrading`).
2. Install the unit:

```bash
sudo cp deploy/congress-dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now congress-dashboard
sudo systemctl status congress-dashboard
```

Logs: `journalctl -u congress-dashboard -f`

## HTTPS (recommended later)

HTTP does not encrypt the login password on the network. When you have a domain:

- Bind Streamlit to localhost only: `DASHBOARD_SERVER_ADDRESS=127.0.0.1`
- Put Caddy or nginx on port 443 with TLS, proxying to `http://127.0.0.1:8501`
- Close public access to port 8501 in `ufw` if only the proxy should be exposed

## Security notes

| Control | Effect |
|---------|--------|
| Login gate | Blocks casual access and crawlers |
| `0.0.0.0` | Listens on all interfaces; required for direct `:8501` access |
| HTTP | Password visible on the wire; prefer HTTPS for production |

Rotate `DASHBOARD_PASSWORD` if the URL is shared widely.
