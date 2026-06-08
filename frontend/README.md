# Congress Trading — React frontend

Vite + React + TypeScript dashboard for the FastAPI JSON API in `src/api/`.

## Stack

- **UI:** Mantine v8
- **Server state:** TanStack Query v5
- **Tables:** TanStack Table v8 (headless)
- **Charts:** Apache ECharts (`echarts-for-react`)
- **Routing:** React Router 6

## Prerequisites

- Node.js 20+
- Python venv with API dependencies (from repo root)

## Development

Run the API and the Vite dev server in **two separate terminals** from the repo root.
Do not paste both blocks into one terminal — the API blocks that shell until you stop it,
so `npm run dev` would never start.

```powershell
# Terminal 1 — FastAPI (default http://127.0.0.1:8000)
.venv\Scripts\python.exe -m src.api

# Terminal 2 — Vite (http://localhost:5173, proxies /api/* to the API)
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173). The Vite dev proxy forwards `/api/*` to `http://127.0.0.1:8000` so session cookies stay same-origin. All `fetch` calls use `credentials: "include"`.

### Auth

When `APP_PASSWORD` is set, the login page posts to `/api/login`. The signed httpOnly session cookie is sent automatically on subsequent requests. Probe session state with `GET /api/session` (no 401).

## Scripts

| Command | Purpose |
|---------|---------|
| `npm run dev` | Vite dev server with `/api` proxy |
| `npm run build` | Production build to `dist/` |
| `npm run preview` | Preview production build |
| `npm run typecheck` | TypeScript check |
| `npm run lint` | ESLint |
| `npm test` | Vitest unit tests |

## Project layout

```
src/
  api/          fetch client, types, TanStack Query hooks, URL param builders (params.ts)
  charts/       pure ECharts option builders
  components/   SidebarLayout, TopBar, UserMenu, ChartCard, shared UI
  routes/       one file per dashboard page (Home, Raw, Review, Members, Tickers, Patterns)
  copy.ts       page copy strings
  styles/       global CSS
```

Layout shell: `SidebarLayout` wraps authenticated routes with `TopBar` + collapsible `SidebarFilters` (lookback/quarters). `RequireAuth` guards the layout; `FilterContext` holds the period slice shared by all pages.

## Adding a new page

1. Add or extend FastAPI routes under `src/api/routers/` (no Streamlit imports).
2. Add response types in `frontend/src/api/types.ts` and a hook in `frontend/src/api/`.
3. Add URL builders in `frontend/src/api/params.ts` if the route takes query params.
4. Implement the route in `frontend/src/routes/` using `PageState`, `SectionIntro`, `ChartCard`, and existing chart/table patterns from Home/Raw.
5. Register the route in `frontend/src/App.tsx`.
6. Add a route test under `frontend/__tests__/routes/` (mock hooks, assert `data-testid`s).
