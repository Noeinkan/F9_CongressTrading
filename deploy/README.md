# VPS app deployment

Run the FastAPI + React app on a Linux VPS so it is reachable at a stable URL such as **http://77.42.70.26/** from any laptop.

Architecture:

- **congress-api** — uvicorn on `127.0.0.1:9001` (`python -m src.api`)
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
- **OGE OCR** (Executive 278-T scanned PDFs): Tesseract + Poppler system packages, plus the Python deps in `requirements.txt` (`pdf2image`, `pytesseract`, `Pillow`)

```bash
# Debian/Ubuntu VPS
sudo apt install -y tesseract-ocr poppler-utils
```

Windows (local ingest): install [Tesseract](https://github.com/UB-Mannheim/tesseract/wiki) and [Poppler for Windows](https://github.com/oschwartz10612/poppler-windows/releases), then add both `bin/` folders to `PATH`. Re-ingest with:

```powershell
.\.venv\Scripts\python.exe -m src.main ingest-oge --force-reparse
```

## `.env` on the VPS

```bash
APP_USERNAME=admin
APP_PASSWORD=<long-random-secret>
APP_SESSION_SECRET=<optional-explicit-secret>
API_SERVER_ADDRESS=127.0.0.1
API_SERVER_PORT=9001
SENATE_EFD_AUTO_DOWNLOAD=0
FMP_API_KEY=<free key from financialmodelingprep.com>
```

When `APP_PASSWORD` is set, the login page appears before any transaction data loads.

**Senate source: FMP, not efdsearch.** From 26 October 2026
efdsearch.senate.gov answers "Access Denied" (Akamai) to every address outside
the US — this VPS and a home connection in Italy alike — so
`SENATE_EFD_AUTO_DOWNLOAD` is off and `publish_senate.ps1` no longer works from
Italy. Senate trades now come from Financial Modeling Prep:

- `FMP_API_KEY` (free plan) turns the source on. The free plan returns only the
  newest 25 Senate rows, so cron runs `poll-senate-fmp` every 30 minutes
  (`deploy/f9-congress-trading.cron`, log `senate-fmp.log`). Each poll merges
  rows into `data/raw/senate/fmp/<eFD uuid>.json`; the nightly `ingest-senate`
  polls once more and parses those files like eFD HTML.
- When a whole poll is new, rows may have scrolled past: one Telegram
  "Senate trades may be missing" message lists the filings to check.
- Filings from 9 October to 25 November 2026 are not recoverable on the free
  plan (it has no older pages).
- If an eFD HTML of the same filing ever lands in `data/raw/senate/`, it wins:
  the FMP rows of that filing are removed at the next ingest.

> **The variables were renamed and the server was not.** Until 12 September 2026
> the VPS `.env` carried `DASHBOARD_USERNAME` / `DASHBOARD_PASSWORD` — the names
> the Streamlit dashboard used. The FastAPI app reads `APP_USERNAME` /
> `APP_PASSWORD`, so those two lines were read by nothing and the board was
> serving every disclosure, the review-queue writes and the ingest trigger to
> anyone who had the IP. The `DASHBOARD_*` lines are inert and can be deleted.
> If you ever see `"auth_required": false` in `/api/health` on a deployment that
> is supposed to be gated, this is the first thing to check.

## Public hostname

The board answers on `https://congress.noeinsolutions.com`, terminated by the
shared nginx edge that already fronts `noeinsolutions.com`. The old
`http://77.42.70.26:8080` still works from inside, but it is a bare IP over
plain HTTP — the login password travels in the clear on it.

The app itself is unchanged: `congress-web` (Caddy) keeps serving
`frontend/dist` and proxying `/api/*` on `:8080`, and nginx simply sits in
front of it holding the certificate. nginx runs in a container, so it reaches
the host Caddy at `172.17.0.1:8080` — the docker0 gateway.

Setting it up, in order:

1. **Add the DNS record.** Cloudflare → `noeinsolutions.com` → DNS → Add
   record: type `A`, name `congress`, IPv4 `77.42.70.26`, Proxy status **DNS
   only** (grey cloud, not orange). Proxying breaks the HTTP-01 challenge in
   step 3. Confirm with `nslookup congress.noeinsolutions.com 1.1.1.1` before
   going on — the rest fails until this answers.

2. **Install the bootstrap vhost.** The real one names a certificate that does
   not exist yet, and nginx refuses to reload with a missing certificate path —
   which would take down every other site on the box, not just this one.

   ```bash
   scp deploy/congress.noeinsolutions.com.bootstrap.conf \
       root@77.42.70.26:/opt/sites/_vhosts/congress.conf
   ssh root@77.42.70.26 'docker exec bep-generator-nginx-1 nginx -t && \
       docker exec bep-generator-nginx-1 nginx -s reload'
   ```

3. **Issue the certificate** over the webroot the edge already mounts:

   ```bash
   ssh root@77.42.70.26 'certbot certonly --webroot -w /var/www/certbot \
       -d congress.noeinsolutions.com --non-interactive --agree-tos \
       -m andrea.aita@noeinsolutions.com'
   ```

4. **Install the real vhost** and reload:

   ```bash
   scp deploy/congress.noeinsolutions.com.conf \
       root@77.42.70.26:/opt/sites/_vhosts/congress.conf
   ssh root@77.42.70.26 'docker exec bep-generator-nginx-1 nginx -t && \
       docker exec bep-generator-nginx-1 nginx -s reload'
   ```

5. **Mark the session cookie Secure**, now that there is TLS to protect it. Set
   `APP_SESSION_HTTPS_ONLY=1` in the VPS `.env` and
   `systemctl restart congress-api`. Do this *only after* step 4 works: with
   the flag on, a browser will not send the cookie over plain HTTP, so
   `:8080` stops being able to hold a login.

6. **Check it**, from a machine that is not the server:

   ```bash
   curl -fsS -o /dev/null -w '%{http_code}\n' https://congress.noeinsolutions.com/
   ```

The demo is a different hostname on the same box —
`congress.demos.noeinsolutions.com`, published through the `hetzner-site`
skill. See [../docs/DEMO.md](../docs/DEMO.md).

For the nightly Telegram alerts add:

```bash
TELEGRAM_BOT_TOKEN=<from @BotFather>
TELEGRAM_CHAT_ID=<from api.telegram.org/bot<token>/getUpdates>
CONGRESS_DASHBOARD_URL=https://congress.noeinsolutions.com
```

The first two are optional: without them `notify-events` / `notify-digest` send
nothing and say so in the log. `CONGRESS_DASHBOARD_URL` turns member and ticker
names in the messages into links to the dashboard; without it they are plain
text. House filings also get a link to the PDF. Senate rows still have no PDF
link: the Senate website only opens a filing after the visitor accepts its
terms, so a direct link lands on its home page. The member link covers those
rows instead. Thresholds are tunable — see the commented block at the end
of `.env.example`. The main README has the full setup walk-through under
"Notifiche Telegram".

Check the channel from the VPS with:

```bash
cd /opt/F9_CongressTrading && ./.venv/bin/python -m src.main notify-test
```

No extra cron entry is needed: `scripts/nightly_ingest.sh` calls both notify
commands, and `notify-digest` self-gates to `CONGRESS_NOTIFY_DIGEST_WEEKDAY`
(Monday by default).

Clicking **Refresh data** in the dashboard sidebar runs the same chain on
demand: ingest, CSV exports, alerts for trades since the last message, and
the 7-day digest on any weekday. If a digest already went out in the last 12
hours the refresh does not send another, so a second click made without
noticing stays silent; the sidebar says when the last one went out and offers
**Send digest again** for the times a second one is wanted. It also shows what
went out, e.g. `Telegram — alerts: quiet · digest: sent today at 14:02`.

## Scheduled job

One cron entry drives everything; its file is `deploy/f9-congress-trading.cron`
(03:30 server time, as the `deploy` user — the same user as the API, so the
Refresh button can overwrite what the night wrote. If started as root, the
script fixes ownership of `data/` and the log, then re-runs itself as `deploy`).

1. **Check whether it is already installed.** On the VPS:
   `cat /etc/cron.d/f9-congress-trading`. If it prints an entry calling
   `nightly_ingest.sh`, compare the time with the repo file and keep whichever
   you prefer; if it says "No such file", go on.
2. **Install it:**

   ```bash
   sudo install -m 0644 /opt/F9_CongressTrading/deploy/f9-congress-trading.cron \
       /etc/cron.d/f9-congress-trading
   ```

   cron picks up `/etc/cron.d` on its own; no restart. The file must stay
   `0644` and owned by root, or cron silently ignores it.
3. **Check the first run** the next morning: `tail -n 20 /var/log/f9-congress-trading/ingest.log`
   should end with `nightly ingest done (rc=0)`. Nothing there means cron never
   fired: re-check step 2's permissions.

After notifications, the same script runs `scripts/run_alpha_flow.sh`. That
asks the SearchForAlpha lab container (`site-alpha-lab-web`) to write the
research digest from this database and F8's DuckDB. It does not download
filings. If the container is not running, the log says so and the night still
counts as a successful ingest. Deploy the lab (`bash deploy.sh` in
`F2_SearchForAlpha_lab`) before expecting a digest file.

The night job runs as `deploy`, which has no docker access. One sudo rule
lets it run that single command and nothing else:

```bash
echo 'deploy ALL=(root) NOPASSWD: /usr/bin/docker exec site-alpha-lab-web python -m lib.alpha_flow' \
  | sudo tee /etc/sudoers.d/f9-alpha-flow
sudo chmod 440 /etc/sudoers.d/f9-alpha-flow && sudo visudo -c
```

Without it the log says "digest not run" every night.

## Firewall

```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
# If you run the dashboard on a non-standard port (see "Listen address" below):
sudo ufw allow 8080/tcp
sudo ufw enable
sudo ufw status
```

## Listen address

`deploy/congress.caddy` listens on `{$CONGRESS_WEB_ADDR::80}`. The systemd
unit sets `Environment=CONGRESS_WEB_ADDR=:8080` out of the box so it works
even when another service (e.g. an existing nginx in a Docker container)
already owns port 80. To switch the dashboard to the canonical :80, edit
`deploy/congress-web.service`, change `CONGRESS_WEB_ADDR=:8080` to
`CONGRESS_WEB_ADDR=:80`, and run `sudo systemctl daemon-reload &&
sudo systemctl restart congress-web`.

## Manual start (development-style)

```bash
cd /opt/F9_CongressTrading
source .venv/bin/activate
python -m src.api   # API on :9001

# separate terminal:
cd frontend && npm ci && npm run build && npm run preview  # or use Caddy in prod
```

Verify from another machine: open `http://<vps-public-ip>/` (Caddy on port 80).

## systemd

### One-shot setup (fresh VPS)

If Caddy is not yet installed and the systemd units have never been set up, run the bootstrap script from the repo root on the VPS (as root or via `sudo`):

```bash
cd /opt/F9_CongressTrading
sudo bash deploy/bootstrap_services.sh
```

It installs Caddy from the official apt repo, creates a `deploy` user, drops the Caddy snippet and systemd units in place, and starts `congress-api` + `congress-web`. It is idempotent — re-running on a configured box is a no-op.

### Manual setup

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
        reverse_proxy 127.0.0.1:9001
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
