# Project Index

On-demand file map. Read this instead of globbing/grepping to locate code.
For CLI commands, data model, and conventions see **AGENTS.md**.

## `src/` — core data layer

| File | Responsibility |
|------|---------------|
| `config.py` | Paths, env vars, constants |
| `db.py` | SQLite connection, schema init, shared queries |
| `utils.py` | Shared utilities (`normalize_key`, text helpers) |
| `main.py` | CLI entrypoint (argparse) |
| `ingest_house.py` | House PTR + FD ingest pipeline |
| `ingest_senate.py` | Senate PTR ingest pipeline |
| `parse_ptr.py` | PTR PDF parsing (layout-sensitive) |
| `parse_fd.py` | Financial Disclosure PDF parsing |
| `download_house_fd.py` | Bulk download from House Clerk |
| `house_coverage.py` | House coverage tracking |
| `ticker_lookup.py` | Ticker/CUSIP resolution |
| `issuer_enrichment.py` | Issuer metadata enrichment |
| `polygon_prices.py` | Polygon.io daily bar fetching + cache |
| `export_csv.py` | CSV export logic |

## `src/api/` — FastAPI service

| File | Responsibility |
|------|---------------|
| `__main__.py` | `python -m src.api` runner (uvicorn; `API_SERVER_PORT` default 9001) |
| `app.py` | `create_app()`, middleware (CORS, session), router registration, `/api/login` |
| `settings.py` | Session cookie + CORS settings (secret, name, https-only, max-age, origins) |
| `security.py` | `verify_credentials`, `login_session`, `logout_session`, `current_user`, `require_auth` |
| `query.py` | `PeriodParams`, `period_params` dep, `Slice`, `get_slice` dep (request-scoped data slice) |
| `repository.py` | Data loading/caching + prep (load_transactions, load_review_queue, load_dataset, period/lookback filters) |
| `filtering.py` | Server-side sort/filter for Raw |
| `serialize.py` | DataFrame/value → JSON-safe records (`iso_date`, `clean`, `records`) |
| `_constants.py` | Column names, SQL queries, paths, sector map |
| `_format.py` | Percent/currency/range formatting, amount sums |
| `_sparklines.py` | Monthly series, KPI sparklines, MoM delta |
| `_home_analytics.py` | Home page analytics |
| `_patterns_analytics.py` | Pattern detection, breakdowns, committee relevance |
| `_tickers_analytics.py` | Ticker leaderboard, profile, price overlay |
| `routers/` | One router per dashboard page (home, raw, review, patterns, members, tickers) |

## `frontend/` — React dashboard

| Path | Responsibility |
|------|---------------|
| `package.json` | npm scripts (`dev`, `build`, `test`, `typecheck`, `lint`) |
| `vite.config.ts` | Vite dev server, `/api` proxy → `127.0.0.1:9001` (reads `API_SERVER_PORT`), Vitest |
| `src/main.tsx` | MantineProvider + QueryClientProvider + RouterProvider |
| `src/App.tsx` | React Router config (login + 6 pages) |
| `src/api/` | `client.ts` (fetch + credentials), `types.ts`, TanStack Query hooks per resource |
| `src/charts/` | Pure ECharts option builders |
| `src/components/` | AppShell, SidebarLayout, TopBar, ChartCard, FilterContext, etc. |
| `src/routes/` | One file per dashboard page |
| `__tests__/` | Vitest unit tests |

## Tests (`tests/`)

`pytest` from repo root. `conftest.py` = fixtures (in-memory DB, sample DataFrames).
Coverage: `test_api_*.py`, `test_re_resolve_tickers.py`.

## Other

`deploy/` — VPS systemd services (congress-api, congress-web), Caddy config, deploy script, logrotate, env-merge helper.
`scripts/` — `nightly_ingest.sh`, `smoke_apis.py`, `count_empty_tickers.py`.
`bootstrap.ps1` / `deploy_local.ps1` — Windows entrypoints.
