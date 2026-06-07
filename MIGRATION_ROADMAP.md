# Migration Roadmap — Streamlit → FastAPI + React

Tracks the rewrite of the Streamlit dashboard into a FastAPI JSON API (`src/api/`)
plus a React frontend. See **CLAUDE.md** for the clean-boundary rule and
**AGENTS.md** for the Python data layer.

**Status legend:** ✅ done · 🚧 in progress · ⬜ not started

_Last assessed: 2026-06-07_

---

## Phase 1 — Carve out the API

Stand up FastAPI in `src/api/` exposing the analytics as JSON. One router per
page. No Streamlit imports under `src/api/` (clean boundary). Self-contained
copies of the pure pieces (`_constants.py`, `_format.py`, `_sparklines.py`,
`repository.py`) kept in sync with `dashboard_shared` until cutover.

### Infrastructure
- [x] ✅ FastAPI app factory + session middleware — `src/api/app.py`
- [x] ✅ Settings / CORS for Vite dev server — `src/api/settings.py`
- [x] ✅ Clean-boundary copies: `_constants.py`, `_format.py`, `_sparklines.py`, `repository.py`
- [x] ✅ Query / slice helpers — `src/api/query.py`, `filtering.py`
- [x] ✅ JSON serialization helpers — `src/api/serialize.py`

### Auth (session cookie, reuses `DASHBOARD_USERNAME`/`DASHBOARD_PASSWORD`)
- [x] ✅ Signed httpOnly session cookie (Starlette `SessionMiddleware`) — `src/api/security.py`
- [x] ✅ Constant-time credential check (port of `dashboard_shared.auth`)
- [x] ✅ `POST /api/login`, `POST /api/logout`, `GET /api/me`, `GET /api/session`
- [x] ✅ `GET /api/health`

### Routes (one per Streamlit page)
- [x] ✅ `GET /api/home/summary` — KPIs + sparklines — `routers/home.py`
- [x] ✅ `GET /api/raw/transactions` — server-side sort/filter/paginate — `routers/raw.py`
- [x] ✅ `GET /api/raw/export.csv` — full filtered/sorted CSV export
- [ ] ⬜ `GET /api/review` — review queue (port `dashboard_pages/review.py`)
- [ ] ⬜ `GET /api/members` — members view (port `dashboard_pages/members.py`)
- [ ] ⬜ `GET /api/tickers` — tickers view (port `dashboard_pages/tickers.py`)
- [ ] ⬜ `GET /api/patterns` — patterns view (port `dashboard_pages/patterns.py`)

**Deferred:** Polygon return-estimate columns on the Raw route (ships core
transaction columns first, matching the current Streamlit CSV export).

---

## Phase 2 — Pick a frontend stack

- [ ] ⬜ Choose stack — leaning React + Vite + TanStack Query (CORS already wired for Vite)
- [ ] ⬜ Component library — Mantine (React)
- [ ] ⬜ Data grid — TanStack Table or AG Grid (for Raw)
- [ ] ⬜ Charts — Apache ECharts or Visx
- [ ] ⬜ Scaffold project (`frontend/` not yet created)

---

## Phase 3 — Layout shell

- [ ] ⬜ Persistent top bar (brand + nav)
- [ ] ⬜ Collapsible left sidebar (filters)
- [ ] ⬜ Content area with real CSS breakpoints
- [ ] ⬜ Auth flow (login page + session probe via `/api/session`)

---

## Phase 4 — Port pages (each port deletes one `dashboard_pages/*.py`)

Order chosen so the hardest UI (Raw grid) comes second, after the API shape is
learned on Home.

- [ ] ⬜ Home (KPIs + sparklines) → delete `dashboard_pages/home.py`
- [ ] ⬜ Raw Data (filterable, exportable grid) → delete `dashboard_pages/raw_data.py`
- [ ] ⬜ Review Queue → delete `dashboard_pages/review.py`
- [ ] ⬜ Members → delete `dashboard_pages/members.py`
- [ ] ⬜ Tickers → delete `dashboard_pages/tickers.py`
- [ ] ⬜ Patterns → delete `dashboard_pages/patterns.py`

---

## Phase 5 — Cut over

- [ ] ⬜ Run API + frontend side by side behind same auth, different port
- [ ] ⬜ Point the dashboard CLI subcommand at the new URL
- [ ] ⬜ Delete `src/dashboard.py`
- [ ] ⬜ Delete `src/dashboard_pages/`
- [ ] ⬜ Remove Streamlit-specific bits of `dashboard_shared` (query-param routing, `st.cache_data` wrappers)
- [ ] ⬜ Promote `src/api/` clean-boundary copies to canonical

---

## Phase 6 — Survives unchanged (no action — guardrail)

These stay untouched; listed so they're not accidentally swept into the rewrite.

- `src/db.py`, `src/ingest_*`, `src/parse_*`, SQLite schema
- Polygon cache, CSV exports, the CLI
- `bootstrap.ps1`, `deploy_local.ps1`, `README.md`
- Every test in `tests/` that doesn't import Streamlit

---

## Progress summary

| Phase | Status |
|---|---|
| 1. API (Home + Raw + auth) | ✅ done |
| 1. API (review/members/tickers/patterns) | ⬜ 4 routes left |
| 2. Frontend stack | ⬜ |
| 3. Layout shell | ⬜ |
| 4. Port 6 pages | ⬜ 0/6 |
| 5. Cut over | ⬜ |
| 6. Data layer preserved | ✅ (guardrail) |

**Next up:** `GET /api/review` (smallest remaining route), then `members` /
`tickers` / `patterns`, then scaffold React.
