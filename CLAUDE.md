# CLAUDE.md

Read this first. It is a map so you don't re-explore the repo each session.
Detailed docs already exist — **don't duplicate, just open them when needed**:

- **AGENTS.md** — full module reference, CLI commands, data model, dashboard architecture, conventions. **Authoritative for the Python data layer + Streamlit dashboard.**
- **README.md** — setup, env vars, legal notes, CSV schema.
- **PROJECT_INDEX.md** — file-by-file index of `src/` (read on demand instead of globbing/grepping).
- **PATTERNS_ROADMAP.md** — planned pattern-detection features.

## What this project is

Python tracker for U.S. House + Senate financial disclosures: PDFs → SQLite → CSV/dashboard.
CLI entrypoint: `python -m src.main <command>` (see AGENTS.md table).
Tests: `pytest` from repo root. Venv: `.venv\Scripts\python.exe`.

## Active migration (read before touching the dashboard)

The Streamlit dashboard is being replaced by a **FastAPI JSON API (`src/api/`) + React frontend** (React not yet scaffolded). Python data layer (db, ingest, parse, schema, Polygon cache, CLI) is untouched.

**Clean-boundary rule — do not break it:** no Streamlit imports anywhere under `src/api/`.
`src/dashboard_shared/__init__.py` eagerly imports Streamlit-coupled code, so **`src/api/` must NOT import from `src.dashboard_shared`.** Instead `src/api/` keeps self-contained copies of the pure pieces (`_constants.py`, `_format.py`, `_sparklines.py`, `repository.py`). Keep those copies in sync with their `dashboard_shared` originals until cutover, when the Streamlit code is deleted and the copies become canonical.

- Run API: `python -m src.api` (env `API_SERVER_PORT`, default 8000).
- Auth: signed httpOnly session cookie (Starlette SessionMiddleware), reuses `DASHBOARD_USERNAME`/`DASHBOARD_PASSWORD`.
- API tests: `tests/test_api_home.py`.
- **Done:** `/api/login|logout|me|session`, `/api/health`, `/api/home/summary`.
- **Remaining routes** (one per Streamlit page, port the pure logic): `/api/raw` (do FIRST — server-side sort/filter/paginate + CSV), `/api/review`, `/api/members`, `/api/tickers`, `/api/patterns`. Then scaffold React, then delete `src/dashboard.py`, `src/dashboard_pages/`, Streamlit bits of `dashboard_shared`.

## Token-saving conventions

- Need a module's purpose or location? Check **PROJECT_INDEX.md** / AGENTS.md tables first — don't grep the tree.
- Keep changes small and targeted; PTR/FD parsing is layout-sensitive — match existing patterns.
- Dashboard page files stay thin (orchestration); logic lives in `dashboard_shared/`. API routers stay thin; logic lives in `repository.py`/`query.py`.
