# Migration Roadmap — Streamlit → FastAPI + React

Tracks the rewrite of the Streamlit dashboard into a FastAPI JSON API (`src/api/`)
plus a React frontend. See **CLAUDE.md** for architecture and
**AGENTS.md** for the Python data layer.

**Status legend:** ✅ done · 🚧 in progress · ⬜ not started

_Last assessed: 2026-06-07 (Phase 6 guardrail verified)_

---

## Phase 1 — Carve out the API

Stand up FastAPI in `src/api/` exposing the analytics as JSON. One router per
page. No Streamlit imports under `src/api/` (clean boundary).

### Infrastructure
- [x] ✅ FastAPI app factory + session middleware — `src/api/app.py`
- [x] ✅ Settings / CORS for Vite dev server — `src/api/settings.py`
- [x] ✅ Data modules: `_constants.py`, `_format.py`, `_sparklines.py`, `repository.py`
- [x] ✅ Query / slice helpers — `src/api/query.py`, `filtering.py`
- [x] ✅ JSON serialization helpers — `src/api/serialize.py`

### Auth (session cookie, uses `APP_USERNAME`/`APP_PASSWORD`)
- [x] ✅ Signed httpOnly session cookie (Starlette `SessionMiddleware`) — `src/api/security.py`
- [x] ✅ Constant-time credential check
- [x] ✅ `POST /api/login`, `POST /api/logout`, `GET /api/me`, `GET /api/session`
- [x] ✅ `GET /api/health`

### Routes (one per former Streamlit page)
- [x] ✅ `GET /api/home/summary` — KPIs + sparklines — `routers/home.py`
- [x] ✅ `GET /api/raw/transactions` — server-side sort/filter/paginate — `routers/raw.py`
- [x] ✅ `GET /api/raw/export.csv` — full filtered/sorted CSV export
- [x] ✅ `GET /api/review/summary` — KPIs + groupbys + paginated rows — `routers/review.py`
- [x] ✅ `GET /api/patterns/summary` — committee relevance, coordinated, call/put, volume, bipartisan — `routers/patterns.py`
- [x] ✅ `GET /api/patterns/committee_relevant?member=` — per-member committee-overlap drill-down
- [x] ✅ `GET /api/patterns/coordinated_transactions?ticker=&pattern=` — disclosure rows behind a coordinated-pattern row
- [x] ✅ `GET /api/members/summary` — leaderboard + KPI sparklines — `routers/members.py`
- [x] ✅ `GET /api/members/{member}/tickers` — per-ticker drill-down for one member
- [x] ✅ `GET /api/members/{member}/committee_relevant` — per-member committee-overlap drill-down
- [x] ✅ `GET /api/tickers` — paginated leaderboard + per-ticker profile + price overlay

**Deferred:** Polygon return-estimate columns on the Raw route (ships core
transaction columns first).

---

## Phase 2 — Pick a frontend stack

- [x] ✅ Choose stack — React + Vite + TanStack Query (CORS already wired for Vite)
- [x] ✅ Component library — Mantine v8
- [x] ✅ Data grid — TanStack Table v8 (headless, for Raw)
- [x] ✅ Charts — Apache ECharts (`echarts-for-react`)
- [x] ✅ Scaffold project — `frontend/` (providers, API client, auth, stub routes, Vitest)

---

## Phase 3 — Layout shell

- [x] ✅ Persistent top bar (brand + nav) — `components/TopBar.tsx` (with `UserMenu` + burger on `xs`)
- [x] ✅ Collapsible left sidebar (filters) — `components/SidebarLayout.tsx` + `components/SidebarFilters.tsx`
- [x] ✅ Content area with real CSS breakpoints
- [x] ✅ Auth flow (login page + session probe via `/api/session`)

---

## Phase 4 — Port pages

- [x] ✅ Home (KPIs + sparklines)
- [x] ✅ Raw Data (filterable, exportable grid)
- [x] ✅ Review Queue
- [x] ✅ Patterns
- [x] ✅ Members
- [x] ✅ Tickers

---

## Phase 5 — Cut over

- [x] ✅ Run API + frontend side by side behind same auth (`APP_*` env vars)
- [x] ✅ Removed `dashboard` / `refresh-dashboard` CLI subcommands (use `python -m src.api` + `npm run dev`)
- [x] ✅ Deleted `src/dashboard.py`
- [x] ✅ Deleted `src/dashboard_pages/`
- [x] ✅ Deleted `src/dashboard_shared/` (Streamlit-specific code)
- [x] ✅ Promoted `src/api/` modules to canonical
- [x] ✅ VPS deploy: Caddy + FastAPI (`deploy/congress-api.service`, `deploy/congress-web.service`, `deploy/congress.caddy`)
- [x] ✅ Renamed `DASHBOARD_*` env vars → `APP_*`

---

## Phase 6 — Survives unchanged (guardrail verified 2026-06-07)

The data layer was audited and confirmed intact after the Streamlit cutover.
These modules stay untouched; listed so they're not accidentally swept into
future rewrites.

**Verified:**
- `src/db.py`, `src/ingest_*`, `src/parse_*`, SQLite schema (all 8 core tables)
- Polygon cache (`src/polygon_prices.py`), CSV exports (`src/export_csv.py`), CLI (`src/main.py`)
- `bootstrap.ps1`, `deploy_local.ps1`, `README.md`
- Zero `import streamlit` statements under `src/` or `tests/`
- `streamlit` and `plotly` removed from `requirements.txt`
- Orphan `.streamlit/config.toml` and stale `.cursor/rules/dashboard-tests-todo.mdc` deleted
- Guardrail enforced by `tests/test_no_streamlit_imports.py`

---

## Progress summary

| Phase | Status |
|---|---|
| 1. API | ✅ done |
| 2. Frontend stack | ✅ done |
| 3. Layout shell | ✅ done |
| 4. Port 6 pages | ✅ done |
| 5. Cut over | ✅ done |
| 6. Data layer preserved | ✅ verified (no data-layer regressions) |

**Migration complete.** The React + FastAPI stack is the sole dashboard.
