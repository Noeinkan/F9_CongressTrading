# CLAUDE.md

Read this first. It is a map so you don't re-explore the repo each session.
Detailed docs already exist — **don't duplicate, just open them when needed**:

- **AGENTS.md** — full module reference, CLI commands, data model, API architecture, conventions. **Authoritative for the Python data layer.**
- **README.md** — setup, env vars, legal notes, CSV schema.
- **PROJECT_INDEX.md** — file-by-file index of `src/` (read on demand instead of globbing/grepping).
- **PATTERNS_ROADMAP.md** — planned pattern-detection features.

## What this project is

Python tracker for U.S. House + Senate financial disclosures: PDFs → SQLite → CSV/dashboard.
CLI entrypoint: `python -m src.main <command>` (see AGENTS.md table).
Tests: `pytest` from repo root. Venv: `.venv\Scripts\python.exe`.

## Dashboard (FastAPI + React)

The Streamlit dashboard has been replaced by a **FastAPI JSON API (`src/api/`) + React frontend** (`frontend/` — Vite + Mantine + TanStack Query/Table + ECharts). Python data layer (db, ingest, parse, schema, Polygon cache, CLI) is untouched.

**Executive branch (OGE):** the pipeline also ingests OGE Form 278-T (periodic transactions) and 278e (annual report) PDFs for the U.S. President (`chamber='Executive'`). 278-T rows land in `transactions` like PTRs; 278e rows land in a dedicated `executive_holdings` table (snapshot of holdings, not trades). Source URLs are hard-coded in `src/oge_source.py`.

**Clean-boundary rule:** no Streamlit imports anywhere under `src/api/`. Analytics live in `src/api/repository.py`, `_constants.py`, `_format.py`, `_sparklines.py`, and `_*_analytics.py`.

- Run API: `python -m src.api` (env `API_SERVER_PORT`, default 9001).
- Run frontend: `cd frontend && npm run dev` (Vite on :5173; proxies `/api/*` to the API; all `fetch` uses `credentials: "include"`).
- Auth: signed httpOnly session cookie (Starlette SessionMiddleware), uses `APP_USERNAME`/`APP_PASSWORD`.
- API tests: `tests/test_api_*.py`. Frontend tests: `cd frontend && npm test`.
- Production: Caddy serves `frontend/dist/` and proxies `/api/*` — see `deploy/README.md`.

## Notifications (Telegram)

`src/notify/` sends **one message per nightly run**, and nothing when nothing
qualifies — silence is the signal. Four event kinds: options, large trades
(disclosed *floor* over the threshold), member clusters on one ticker, filings
past the 45-day STOCK Act deadline. Plus a self-gating weekly digest that also
reports pipeline staleness.

- CLI: `notify-events`, `notify-digest`, `notify-test`, `notify-failure` (all take `--dry-run`).
- Wired into `scripts/nightly_ingest.sh`; **no second cron entry needed** — the digest gates itself on `CONGRESS_NOTIFY_DIGEST_WEEKDAY`. Cron file: `deploy/f9-congress-trading.cron`.
- The sidebar Refresh job ends with `src/post_ingest.py` (exports → alerts → digest with `force=True` and a 12 h `cooldown_hours`, so a double click sends one digest; `POST /api/admin/send-digest` is the explicit resend, no cooldown). Keep its steps in step with the nightly script; tests patch `src.post_ingest.run_post_ingest` so a refresh test never writes CSVs or calls Telegram.
- **Invariant to preserve:** the `last_transaction_id` high-water mark advances *only* after Telegram confirms delivery, so an outage delays alerts instead of dropping them (`tests/test_notify_service.py` locks this down).
- Rows filed more than `CONGRESS_NOTIFY_MAX_FILING_AGE_DAYS` (30) ago are loaded but never alerted on, so a backfill (the first Senate download reaches back to 2023) stays silent (`recent_filings` in `events.py`).
- Detection rules are pure functions over a prepared frame — add a detector in `events.py`, never inline in `service.py`.
- Reuses `repository._prepare_transactions` and `_patterns_analytics.detect_coordinated_trades` so an alert can't disagree with the dashboard.

## Token-saving conventions

- Need a module's purpose or location? Check **PROJECT_INDEX.md** / AGENTS.md tables first — don't grep the tree (includes `frontend/` component/chart/route tables).
- Keep changes small and targeted; PTR/FD parsing is layout-sensitive — match existing patterns.
- API routers stay thin; logic lives in `repository.py`/`query.py`.
- **Frontend page recipe:** `PageState` + `SectionIntro` + `ChartCard`; KPIs via `KpiTile` only (optional detail/sparkline/delta).
- **Frontend chart recipe:** pure option builder in `frontend/src/charts/` + thin wrapper that uses `EChartsChart` (do not import `echarts-for-react` elsewhere).
- **Entity navigation:** `MemberLink` / `TickerLink` / `entityLinks.ts` — reuse before inventing new link helpers.
