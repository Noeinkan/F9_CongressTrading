# Public demo mode

A stranger clicks a link on [noeinsolutions.com/builds.html](https://noeinsolutions.com/builds.html)
and lands inside a working copy of the dashboard: real disclosures, real
members, real tickers, frozen at a date and read-only. No sign-up, no key, no
install, and nothing they do changes what the next visitor sees.

This file is how it works, how to run it, and how to switch it off.

> **Status as of 14 September 2026: live** at
> <https://congress.demos.noeinsolutions.com/demo>. See [Deploying it](#deploying-it)
> for how it runs and how to redeploy.

## The short version

| | |
| --- | --- |
| **Kill switch** | `DEMO_MODE` — unset or false and none of this exists |
| **Data** | `demo/fixtures/demo-snapshot.sqlite.gz`, captured 2026-09-12 |
| **What is in it** | 13,647 transactions, 105 members, 1,315 tickers, 2,885 review rows |
| **Writes** | all refused, by middleware, for the whole `/api/*` surface |
| **Entry point** | `/demo` — signs the visitor in and drops them on the dashboard |
| **Cost per visit** | none: no API key is used and no outbound call is made |
| **Resets** | nothing to reset; the snapshot is never written to |

## Why the data is frozen

The live tracker downloads PDFs from the House Clerk, parses them, and calls
Polygon and OpenFIGI to resolve tickers. None of that can happen on a public
demo: it needs API keys, it puts traffic on a government site on a stranger's
behalf, and it would make the demo's contents depend on whether a scrape
succeeded that morning.

So the demo reads a **snapshot**: a copy of the database, trimmed and committed
to the repo. With every secret unset and the network blocked, every page still
renders — that is the property the snapshot exists to guarantee.

The snapshot is trimmed because the live database is ~146 MB, almost all of it
daily price bars. Keeping transactions from 2025-01-01 and price bars from
2024-10-01 gives 42 MB, which compresses to **9.1 MB** — small enough to commit
without turning every refresh into a large entry in git history.

The capture also drops three filings whose source path pointed at a pytest temp
directory. Those are test rows that leaked into the live database; they are not
real disclosures, and they are worth cleaning out of the live database too.

## Running it locally

```bash
# 1. Expand the committed fixture (idempotent; writes to data/db/, gitignored)
python scripts/unpack_demo_snapshot.py

# 2. Run the API as the demo
DEMO_MODE=1 \
CONGRESS_DB_PATH=data/db/demo-snapshot.sqlite \
APP_USERNAME=demo APP_PASSWORD=demo \
python -m src.api

# 3. Run the frontend as usual
cd frontend && npm run dev
```

Then open **http://localhost:5173/demo** — not `/`. That is the one-click door;
`/` still shows the login form, where `demo` / `demo` also works.

On Windows PowerShell, set the variables first:

```powershell
$env:DEMO_MODE=1
$env:CONGRESS_DB_PATH="data/db/demo-snapshot.sqlite"
$env:APP_USERNAME="demo"; $env:APP_PASSWORD="demo"
.\.venv\Scripts\python.exe -m src.api
```

## Every environment variable

| Variable | Default | What it does |
| --- | --- | --- |
| `DEMO_MODE` | *unset* (off) | The kill switch. `1`/`true`/`yes`/`on` turns the demo on; anything else, including unset, leaves the app exactly as it was. |
| `DEMO_USERNAME` | `demo` | Name the minted session is recorded under. |
| `DEMO_PASSWORD` | `demo` | The published password. It guards nothing — it is printed on the landing card on purpose. |
| `DEMO_SNAPSHOT_DATE` | from `demo/demo.json` | Overrides the capture date shown on the banner. |
| `DEMO_SOURCE_URL` | the Builds page | Where the banner's "About this build" link goes. Blank hides the link. |
| `CONGRESS_DB_PATH` | `data/db/congress_trades.sqlite` | Which SQLite file **any** process serves. This is what lets the demo and the live tracker run from one checkout. |

`APP_USERNAME` / `APP_PASSWORD` are the existing login gate and are unchanged.
Setting `APP_PASSWORD` is what makes the login page appear at all; the demo
wants it set, so that a visitor arriving at `/` meets a door rather than the
data.

## How it is built

Everything demo-specific is under `src/demo/`. The rest of the app has three
lines of awareness of it.

| File | Role |
| --- | --- |
| [src/demo/config.py](../src/demo/config.py) | Reads the environment and the manifest. |
| [src/demo/readonly.py](../src/demo/readonly.py) | Middleware refusing every write while the demo is on. |
| [src/demo/router.py](../src/demo/router.py) | `GET /api/demo/status`, `POST /api/demo/session`. |
| [src/api/app.py](../src/api/app.py) | Registers the middleware and the router. Two lines. |
| [src/config.py](../src/config.py) | `CONGRESS_DB_PATH` override. One line. |

**The guard is a middleware, not a per-route dependency.** The dashboard has
five mutating endpoints today — three review-queue actions and two refresh
controls, one of which starts an ingest run. A middleware covers a sixth one
added next year without anyone remembering to cover it.

Two endpoints are deliberately exempt: `/api/login` and `/api/logout`. Session
handling is not data, and blocking logout would trap the visitor inside the
demo.

**`POST /api/demo/session` 404s when the demo is off** — not 403. A production
deployment does not advertise that the route exists.

**`GET /api/demo/status` answers everywhere**, returning `{"enabled": false}`
off-demo. That is what lets one frontend build serve both the private dashboard
and the public demo: the page asks the server which one it is talking to.

### On the frontend

| File | Role |
| --- | --- |
| [frontend/src/routes/DemoEntry.tsx](../frontend/src/routes/DemoEntry.tsx) | The `/demo` route: mints the session, redirects to `/`. Falls back to `/login` where there is no demo. |
| [frontend/src/components/DemoBanner.tsx](../frontend/src/components/DemoBanner.tsx) | The honesty line. Dismissible per tab, not per browser. |
| [frontend/src/api/demo.ts](../frontend/src/api/demo.ts) | `useDemoStatus`, `useDemoSignIn`. |

Three places change their behaviour when the status says demo:

- **The nav drops `/executive`.** That page needs OGE filings the snapshot has
  none of — and the live database has none either. A nav item leading to a blank
  page makes a demo read as broken rather than as deliberately limited. The list
  comes from the server (`hiddenRoutes`), so it is data, not a hardcoded rule.
- **The Review queue goes read-only.** It already had a read-only path for a
  non-SQLite source; demo mode folds into it, with its own explanation. The
  queue is still worth showing — the triage workflow is part of what the project
  *is*.
- **The Admin refresh block disappears.** It runs the ingest against the House
  Clerk. The API would refuse it anyway; the button is hidden so a stranger
  never clicks something that fails.

## Refreshing the snapshot

```bash
python scripts/freeze_demo_data.py            # defaults: transactions from 2025-01-01
python scripts/freeze_demo_data.py --since 2024-01-01 --bars-since 2023-10-01
```

It copies the live database, trims the window, cascades the deletes, scrubs, and
writes both the fixture and the capture date into `demo/demo.json`. Then commit
the fixture and redeploy.

Widening the window costs size quickly, because price bars dominate: the same
capture from 2024-01-01 is 13.8 MB compressed instead of 9.1 MB.

**What gets scrubbed.** `filings.raw_document_path` holds absolute paths from
the ingest machine (`C:\Users\andre\...`). It cannot simply be blanked, because
the API reads the parent folder and the file stem out of it to rebuild the link
to the original PDF on disclosures-clerk.house.gov. So the capture keeps the
last three segments and discards the rest: the links still resolve, the layout
of a private machine does not ship. The `source_url` beside it is kept as-is —
those are government URLs, and they are the provenance the demo claims.

## Switching it off

Set `DEMO_MODE=0`, or remove it, and restart. That is the whole procedure.

- `POST /api/demo/session` starts returning 404, so no demo session can be
  minted.
- The read-only middleware stands down; writes go back to the normal auth gate.
- `/api/demo/status` returns `{"enabled": false}`, so the banner stops
  rendering, the full nav comes back and the Review actions return.

There is no client-side flag to get wrong. The frontend asks the server.

## Deploying it

The demo runs **apart from** the live tracker, not as a mode of it — so a demo
visitor has no path at all to the live database. It is published through the
`hetzner-site` skill as two containers behind the shared nginx edge, with
everything in [`.deploy/`](../.deploy/):

| Container | Role |
| --- | --- |
| `site-congress-demo-web` | nginx serving the React build; the only container on the `edge` network, so the only one the internet can reach. Forwards `/api/*` to the one below. |
| `site-congress-demo-api` | FastAPI with `DEMO_MODE=1`, on an internal Docker network with **no route out** — the "no outbound call" promise is enforced, not just intended. Expands the committed fixture into a RAM disk at every start, so a restart always serves exactly the snapshot in git. |

Neither container reads the repo `.env`: that file carries the real password
and the Polygon key, and the demo must have neither. The one secret it has,
`APP_SESSION_SECRET`, lives in `/opt/sites/congress-demo/.env` on the server
(mode 0600) and nowhere in git.

**The slug is `congress-demo`, not `congress`.** `hetzner-site` names the vhost
after the slug, and `/opt/sites/_vhosts/congress.conf` is already taken by the
production `congress.noeinsolutions.com`. A slug of `congress` would overwrite it.

To redeploy, from the repo root on a machine with the skill installed:

```bash
git push origin main                                         # the server builds from GitHub, not from this checkout
bash ~/.claude/skills/hetzner-site/bin/site-deploy.sh --dry-run
bash ~/.claude/skills/hetzner-site/bin/site-deploy.sh        # build, health check, certificate, vhost, smoke test
bash ~/.claude/skills/hetzner-site/bin/site-deploy.sh --rollback
```

The root `deploy.sh` is **not** this: it is the private tracker's own wrapper.
Uncommitted work in the checkout never ships, because the server clones `main`.

`deploy/congress-demo-api.service` is the earlier plan — the same API as a
host systemd unit on port 9101 beside the live one. It was never installed:
the edge can only reach containers, and the container needs no host checkout.
It is superseded by `.deploy/`.

## Publishing history

- 2026-09-12 — built and tested locally; blocked on the `*.demos` DNS record.
- 2026-09-14 — DNS resolved; published at
  <https://congress.demos.noeinsolutions.com/demo> from commit `1dee394`. The
  three Builds-page captures were re-shot against the live demo with
  `shotkit.config.mjs`, which now targets it.
