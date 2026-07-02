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

## Token-saving conventions

- Need a module's purpose or location? Check **PROJECT_INDEX.md** / AGENTS.md tables first — don't grep the tree.
- Keep changes small and targeted; PTR/FD parsing is layout-sensitive — match existing patterns.
- API routers stay thin; logic lives in `repository.py`/`query.py`.
