# Public demo mode

A stranger clicks a link on [noeinsolutions.com/builds.html](https://noeinsolutions.com/builds.html),
types their email, types the 6-digit code that arrives, and lands inside a
working copy of the dashboard: real disclosures, real members, real tickers,
frozen at a date and read-only. They get **one 45-minute session**, and you can
see who came and what they opened.

This file is how it works, how to run it, how to switch it on for the first
time, and how to switch it off.

> **Status as of 16 September 2026:** the open demo (no sign-up) is live at
> <https://congress.demos.noeinsolutions.com/demo>. The email gate described here
> is built and tested but **not deployed yet** — see [Switching the gate on](#switching-the-gate-on).

## The short version

| | |
| --- | --- |
| **Kill switch** | `DEMO_MODE` — unset or false and none of this exists |
| **Way in** | `/demo` → an email form → one email with a 6-digit code and a link → the dashboard |
| **Session** | 45 minutes of wall-clock time from the first sign-in, once per address |
| **Data** | `demo/fixtures/demo-snapshot.sqlite.gz`, captured 2026-09-12 |
| **What is in it** | 13,647 transactions, 105 members, 1,315 tickers, 2,885 review rows |
| **Locked** | the two CSV downloads, and the Review-queue actions |
| **Removed** | refresh / ingest, deploy, the Telegram digest |
| **Writes** | all refused, by middleware, for the whole `/api/*` surface |
| **Who used it** | `/admin` on the demo site, plus one email to you per new sign-up |
| **Cost per visit** | no API key and no outbound call, except one or two sign-in emails (at most 200 a day) |

## What a visitor meets

1. **The email form** (`/access`, where `/demo` sends them). Under the field, three
   short paragraphs say what is stored, why, and for how long.
2. **One email** from `support@noeinsolutions.com` with a 6-digit code and a link.
   Both work once, for 15 minutes. The link opens a page with a "Sign in" button
   rather than signing in by itself: company mail filters open every link in an
   email to scan it, and would otherwise use it up before the person clicks.
3. **The dashboard**, with a banner that says it is a demo, shows the snapshot
   date, and counts down the time left. Dismissing the banner hides the notice
   but keeps the clock.
4. **Locked controls** stay visible. Clicking "Download CSV" or a Review action
   opens one notice saying what that feature is and that it comes with full
   access. The server refuses the request whatever the page does.
5. **After 45 minutes** every page goes to "Your 45 minutes with the demo are up",
   with a button to write to `support@noeinsolutions.com`. There is no "start
   again". Asking for a new code with the same address sends that inbox a note
   saying its session has ended, and the page shows the usual "check your inbox" —
   so the form never reveals which addresses have already had a session.

Coming back inside the 45 minutes — a closed tab, another device — picks up the
same session with the time that is left. It never restarts the clock.

**How firm "once" is.** A session belongs to a mailbox, not a spelling:
`Jane.Doe+demo@gmail.com` and `janedoe@gmail.com` share one. Throwaway-inbox
services are refused. A second *real* mailbox does get a second session; that is
the honest ceiling of an email gate. The rule also lasts only as long as the
address is kept: someone deleted after 365 days without a visit can have another.

## Feature tiers

| Tier | Features | Mechanism |
| --- | --- | --- |
| **Open** | Home, Senate, Members, Tickers (price overlay included), Patterns, the Raw table, the Review queue (reading) | Nothing beyond the session. Every read is local to the snapshot: price charts read stored bars, not Polygon. |
| **Metered** | *none* | No page does paid or heavy work, so there is no per-session budget. The one global cap is on sign-in emails. |
| **Locked** | CSV downloads (Home net trade, Raw export); Review-queue resolve / accept / dismiss | Visible; refused by the server with `DEMO_LOCKED` and the feature; the click is recorded. Decided by the owner on 2026-09-16, although the data is public. |
| **Removed** | Refresh / ingest, deploy controls, Telegram digest | The admin router is not registered while `DEMO_MODE` is on, and the API container has no route to the internet. |
| **Hidden** | `/executive` | The snapshot has no OGE filings; a nav item leading to a blank page reads as broken. |

The locked list lives in one place, [src/demo/tiers.py](../src/demo/tiers.py). The
status endpoint hands it to the app, so the button, the notice and the server
always describe the same thing.

## What is recorded, and the admin page

Recorded against each address: when it asked for a code, when it signed in, the
IP it signed in from, which pages it opened (the same page within 10 minutes
counts once), which members and tickers, and which locked features it clicked.

**`/admin`** on the demo site (for example
`https://congress.demos.noeinsolutions.com/admin`) shows it:

- totals: signed up, sessions running now, new and seen this week, locked clicks,
  emails sent in the last 24 hours against the 200 cap;
- one row per person: status, first sign-in, session start and end, last seen,
  pages, members and tickers opened, locked clicks, the six things they opened
  most, last IP;
- the latest 100 events, and CSV exports of both.

Three actions per person:

- **Grant another session** — the only way anyone gets a second one. On a running
  session it adds 45 minutes. Otherwise it signs their browsers out and gives them
  a fresh 45 minutes that starts at their next sign-in (and lifts a revoke).
- **Revoke** — signs every browser of that address out at once.
- **Delete** — removes the person and everything recorded about them. This is how
  a deletion request is honoured.

The page is a 404 until `DEMO_ADMIN_TOKEN` is set on the server. You sign in with
the token in a form (never in the address bar, where it would land in the server
log); the cookie that keeps you signed in lasts 12 hours and works only under
`/admin`.

**Retention.** People unseen for 365 days are deleted with their usage, by an
hourly clean-up. Addresses that asked for a code but never signed in are deleted
after 30 days, because anyone can type anyone's address.

**The sign-up email.** With `DEMO_NOTIFY_EMAIL` set, you get one short email each
time a new address starts its first session, with a link to `/admin`. Resuming a
session or a second session does not send another.

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

# 2. Run the API as the demo, with sign-in codes printed in its log instead of mailed
DEMO_MODE=1 \
DEMO_MAIL_BACKEND=console \
CONGRESS_DB_PATH=data/db/demo-snapshot.sqlite \
python -m src.api

# 3. Run the frontend as usual
cd frontend && npm run dev
```

Then open **http://localhost:5173/demo**, type any address, and copy the code
from the API's terminal (the line starts `DEMO_MAIL_BACKEND=console, not sending`).
Sign-ins are kept in `data/demo-access/access.sqlite3` (gitignored); delete that
file to start over.

To see the admin page locally, also set `DEMO_ADMIN_TOKEN` to any 24+ character
string and open **http://localhost:9001/admin** — the Vite dev server does not
forward `/admin`.

To skip the gate entirely, add `DEMO_ACCESS_GATE=0`: the demo is then open to
anyone and nothing is recorded, but the locks and the read-only guard still hold.
Never set that on the server.

On Windows PowerShell, set the variables first:

```powershell
$env:DEMO_MODE=1
$env:DEMO_MAIL_BACKEND="console"
$env:CONGRESS_DB_PATH="data/db/demo-snapshot.sqlite"
.\.venv\Scripts\python.exe -m src.api
```

## Every environment variable

| Variable | Default | What it does |
| --- | --- | --- |
| `DEMO_MODE` | *unset* (off) | The kill switch. `1`/`true`/`yes`/`on` turns the demo on; anything else, including unset, leaves the app exactly as it was. |
| `DEMO_SNAPSHOT_DATE` | from `demo/demo.json` | Overrides the capture date shown on the banner. |
| `DEMO_SOURCE_URL` | the Builds page | Where the banner's "About this build" link goes. Blank hides the link. |
| `CONGRESS_DB_PATH` | `data/db/congress_trades.sqlite` | Which SQLite file **any** process serves. This is what lets the demo and the live tracker run from one checkout. |
| `DEMO_ACCESS_GATE` | on | `0` opens the demo to anyone, unrecorded. Local runs only. |
| `DEMO_ACCESS_DB` | `data/demo-access/access.sqlite3` | The sign-in store. On the server, a Docker volume. |
| `DEMO_SESSION_MINUTES` | `45` | Length of the one session. `0` is raised to 1: it never means "no limit". |
| `DEMO_RETENTION_DAYS` | `365` | People unseen this long are deleted with their usage. |
| `DEMO_CODE_MINUTES` | `15` | How long a code or link works. |
| `DEMO_CODE_ATTEMPTS` | `5` | Wrong codes before that code is dead. |
| `DEMO_CODES_PER_EMAIL_PER_HOUR` | `3` | Sign-in emails to one address per hour. |
| `DEMO_CODES_PER_HOUR` / `_PER_DAY` | `60` / `200` | Sign-in emails in total. Neo allows the mailbox about 1,000 a day, shared with your own mail and the other demos; this keeps a bot from getting it throttled. |
| `DEMO_SIGNUPS_PER_IP_PER_DAY` | `5` | New addresses from one connection per day. |
| `DEMO_BLOCKED_EMAIL_DOMAINS` | *empty* | Comma list of extra throwaway domains to refuse. |
| `DEMO_PUBLIC_URL` | the request's host | Base of the link in the email. |
| `DEMO_CONTACT_EMAIL` | `support@noeinsolutions.com` | On the privacy note, the ended page and the emails. |
| `DEMO_MAIL_BACKEND` | `smtp` | `console` prints the email in the log instead of sending. |
| `DEMO_MAIL_RELAY` | *empty* | `host:port` of the relay container. Empty dials the mail server directly (fine on a laptop). |
| `DEMO_SMTP_SECURITY` | `auto` | `auto` picks implicit TLS for 465 and STARTTLS otherwise. |
| `NEO_SMTP_HOST` / `_PORT` / `_USER` / `_PASS` | — | **Secret.** The Neo mailbox, same names as Capsar; `SMTP_*` is the fallback for each. |
| `EMAIL_FROM` | the mailbox | **Secret file.** `support@noeinsolutions.com`, an alias of the mailbox. |
| `DEMO_ADMIN_TOKEN` | *unset* | **Secret.** At least 24 characters; unset and `/admin` is a 404. |
| `DEMO_NOTIFY_EMAIL` | *unset* | **Secret file.** Where the one-line email per new sign-up goes; unset sends nothing. |

With the gate on and `DEMO_MAIL_BACKEND=smtp`, the API **refuses to start**
without the mail host, user and password. On the server the health check then
fails and the deploy rolls back to the previous version, so a gate nobody can
pass never goes live.

## How it is built

Everything demo-specific is under `src/demo/`. The rest of the app has a handful
of lines of awareness of it.

| File | Role |
| --- | --- |
| [src/demo/config.py](../src/demo/config.py) | Reads `DEMO_MODE` and the manifest. |
| [src/demo/tiers.py](../src/demo/tiers.py) | The locked and removed lists. One list, on the server. |
| [src/demo/readonly.py](../src/demo/readonly.py) | Middleware: refuses locked features (`DEMO_LOCKED`) and every other write (`DEMO_READ_ONLY`). |
| [src/demo/router.py](../src/demo/router.py) | `GET /api/demo/status`: snapshot, hidden routes, locked list, session length, the visitor's access. |
| [src/demo/access/settings.py](../src/demo/access/settings.py) | Every gate setting from the environment; `problems()` stops the start. |
| [src/demo/access/emails.py](../src/demo/access/emails.py) | Address validation, the canonical form, throwaway domains. |
| [src/demo/access/store.py](../src/demo/access/store.py) | SQLite: visitors, codes, grants, events. The session clock. |
| [src/demo/access/mailer.py](../src/demo/access/mailer.py) | SMTP through the relay (standard library only), or the console. |
| [src/demo/access/relay.py](../src/demo/access/relay.py) | The relay container's whole program. |
| [src/demo/access/messages.py](../src/demo/access/messages.py) | The privacy paragraphs and the three emails. |
| [src/demo/access/service.py](../src/demo/access/service.py) | The gate's state, the usage hook, the hourly purge, the start-up mail check. |
| [src/demo/access/gate.py](../src/demo/access/gate.py) | The middleware in front of every request, and the sign-in API. |
| [src/demo/access/admin.py](../src/demo/access/admin.py) | `/admin` and its CSV exports. |
| [src/api/app.py](../src/api/app.py) | Registers the gate (outermost), the guard and the routers; leaves the admin router out on the demo. |
| [src/api/security.py](../src/api/security.py) | Treats the gate's verified address as the signed-in user. |
| [src/config.py](../src/config.py) | `CONGRESS_DB_PATH` override. One line. |

**The gate is a middleware, and it runs first.** A browser without a running
session never reaches the session cookie, a router or the snapshot. Open without
a session: `/api/health`, `/api/demo/status` (the sign-in page reads it),
`/api/demo/access/*`, `/admin` (it has its own token) and `/robots.txt`.
Everything else — including `/openapi.json` — answers `401 DEMO_SIGNED_OUT`, or
`403 DEMO_EXPIRED` once the time is up.

**The read-only guard is a middleware too, not a per-route dependency.** A
mutating endpoint added next year is covered without anyone remembering to cover
it.

### The sign-in API

All JSON; all 404 when the demo or the gate is off.

| Route | What it does |
| --- | --- |
| `POST /api/demo/access/request` | Sends the code and link. `400 INVALID_EMAIL` / `BLOCKED_DOMAIN`, `429 RATE_LIMITED`, `503 MAIL_FAILED` (a failed send is not counted against any limit). |
| `POST /api/demo/access/code` | Signs in with the code. `400 WRONG_CODE` (with attempts left) or `CODE_DEAD`, `403 DEMO_EXPIRED`. |
| `GET /api/demo/access/link?t=` | Who a link is for. Does not sign in, does not use the link up. `410 LINK_DEAD`. |
| `POST /api/demo/access/link` | Signs in with the link. |
| `POST /api/demo/access/signout` | Signs this browser out. |

### On the frontend

| File | Role |
| --- | --- |
| `frontend/src/routes/DemoEntry.tsx` | `/demo`, the URL on the landing card: sends the visitor to sign-in, the dashboard or the ended page. Falls back to `/login` where there is no demo. |
| `frontend/src/routes/Access*.tsx` | `/access` (email, then code), `/access/verify` (the link's button), `/access/ended`. |
| `frontend/src/components/DemoBanner.tsx` | The honesty line and the countdown; the clock survives a dismiss. |
| `frontend/src/components/DemoWall.tsx` | One notice for every refusal code the API sends. `apiFetch` (`frontend/src/api/client.ts`) passes each `DEMO_*` code to it. |
| `frontend/src/hooks/useDemoLock.ts` | Tells a button whether its feature is locked, and opens the same notice a server refusal would. |
| `frontend/src/api/demo.ts` | The status query and the sign-in calls. |

Places that change behaviour when the status says demo:

- **The nav drops `/executive`** (the list comes from the server as `hiddenRoutes`).
- **The CSV buttons and the Review actions** stay visible and open the notice
  instead of acting.
- **The Admin refresh block disappears.** It runs the ingest against the House
  Clerk, and those routes do not exist in the demo process.

## Deploying it

The demo runs **apart from** the live tracker, not as a mode of it — so a demo
visitor has no path at all to the live database. It is published through the
`hetzner-site` skill as three containers behind the shared nginx edge, with
everything in [`.deploy/`](../.deploy/):

| Container | Role |
| --- | --- |
| `site-congress-demo-web` | nginx serving the React build; the only container on the `edge` network, so the only one the internet can reach. Forwards `/api/*`, `/admin` and `/robots.txt` to the API. |
| `site-congress-demo-api` | FastAPI with `DEMO_MODE=1`, on an internal Docker network with **no route out** — the "no outbound call" promise is enforced, not just intended. Expands the committed fixture into a RAM disk at every start, so a restart always serves exactly the snapshot in git. Keeps the sign-ins on the `access` volume, which survives restarts and redeploys. |
| `site-congress-demo-relay` | The one door out: forwards every connection to `smtp0001.neo.space:587` and nowhere else. Its image holds that one Python file; it reads no `.env`. The API switches the connection to encryption and checks Neo's certificate straight through it, so the relay only ever carries encrypted bytes. |

The secrets live in `/opt/sites/congress-demo/.env` on the server (mode 0600) and
nowhere in git: `APP_SESSION_SECRET`, the `NEO_SMTP_*` lines, `EMAIL_FROM`,
`DEMO_ADMIN_TOKEN`, `DEMO_NOTIFY_EMAIL`. Only the API container reads that file;
none of those names may appear under `environment:` in `compose.yml`, because a
key there overrides the one in the file.

**Never run `docker compose down -v` on this site**: `-v` deletes the `access`
volume, and with it every sign-in and the whole usage log.

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

## Switching the gate on

Do these in order. The API refuses to start until steps 2–4 are done, and a
failed start rolls the deploy back — so the open demo keeps running until they are.

1. **Check the sender alias.** `support@noeinsolutions.com` must be an alias of the
   Neo mailbox you log in with. It was made for the SearchForAlpha demo, so there
   is normally nothing to do. To check: sign in to Neo Webmail with that mailbox
   (or to the Neo Email Control Panel as the domain admin), open the mailbox's
   **email alias** settings, and look for `support@`. Neo's walkthrough:
   <https://support.neo.space/hc/en-us/articles/14465294068761-Email-Alias>.
   *If it is missing, step 6 will say "553 … not owned by user".*
2. **Copy the mail lines from Capsar.** Open `C:\Users\andre\Downloads\W3_capsar_io\.env`
   and copy the lines starting with `NEO_SMTP_HOST`, `NEO_SMTP_USER` and
   `NEO_SMTP_PASS`. **Use port 587, not the 465 written there**: the Hetzner server
   blocks outgoing 465, and a send on it waits and times out.
3. **Make an admin token**, at least 24 characters:
   `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Keep it in your
   password manager.
4. **Write the secrets on the server.** Replace the placeholders:

   ```bash
   ssh root@77.42.70.26
   cat >> /opt/sites/congress-demo/.env <<'EOF'
   NEO_SMTP_HOST=smtp0001.neo.space
   NEO_SMTP_PORT=587
   NEO_SMTP_USER=the-mailbox-address
   NEO_SMTP_PASS='the-mailbox-password'
   EMAIL_FROM=support@noeinsolutions.com
   DEMO_ADMIN_TOKEN=the-token-from-step-3
   DEMO_NOTIFY_EMAIL=the-address-that-should-get-sign-up-emails
   EOF
   chmod 600 /opt/sites/congress-demo/.env
   ```

   **Keep the single quotes around the password.** Docker Compose reads a `$` in
   this file as the start of a variable name, so a password containing `$` reaches
   the demo cut short and Neo answers "535 authentication failed"; quoted, it
   arrives exactly as written.
5. **Commit, push and deploy** (the commands in [Deploying it](#deploying-it)).
6. **Check the mail line in the log**:
   `ssh root@77.42.70.26 "docker logs site-congress-demo-api 2>&1 | grep 'demo access'"`.
   Right after every start the API signs in to Neo once and writes either
   "mail server … reachable" or "NOT usable" with the reason. "timed out" means a
   blocked port or a relay that is down; "535" a wrong user or password;
   "553 … not owned" means `support@` is not an alias of the mailbox.
   A green health check does **not** prove mail works — only this line does.
7. **Try it as a stranger.** Open <https://congress.demos.noeinsolutions.com/demo>
   in a private window: it should show the email form. Use your own address; the
   code should arrive within a minute from `support@noeinsolutions.com`, and the
   sign-up email should reach `DEMO_NOTIFY_EMAIL`. Then open `/admin`, sign in with
   the token, and find yourself in the table.
8. **Re-shoot the landing captures** if you want the countdown in frame
   (`shotkit.config.mjs` explains how to hand it your session cookie), and commit
   the landing-page note change prepared in `W8_NoeinSolLandingPage`.

## Refreshing the snapshot

```bash
python scripts/freeze_demo_data.py            # defaults: transactions from 2025-01-01
python scripts/freeze_demo_data.py --since 2024-01-01 --bars-since 2023-10-01
```

It copies the live database, trims the window, cascades the deletes, scrubs, and
writes both the fixture and the capture date into `demo/demo.json`. Then commit
the fixture and redeploy. The sign-in store is untouched by a refresh.

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

- Every demo route answers 404: the sign-in API, `/admin`.
- The gate is not installed; the read-only guard stands down; the admin router
  (refresh, deploy, digest) is registered again.
- `/api/demo/status` returns `{"enabled": false}`, so the banner stops
  rendering, the full nav comes back and the Review actions return.

There is no client-side flag to get wrong. The frontend asks the server.

To keep the demo but take the gate down (say, mail is broken and you would rather
be open than closed), set `DEMO_ACCESS_GATE=0` in `.deploy/compose.yml` and
redeploy. The demo is then open to anyone and records nothing.

## Publishing history

- 2026-09-12 — built and tested locally; blocked on the `*.demos` DNS record.
- 2026-09-14 — DNS resolved; published at
  <https://congress.demos.noeinsolutions.com/demo> from commit `1dee394`, open to
  anyone. The three Builds-page captures were re-shot against the live demo with
  `shotkit.config.mjs`.
- 2026-09-16 — email gate, 45-minute session, locked CSV downloads and Review
  actions, admin page and mail relay built and tested; not yet deployed.
