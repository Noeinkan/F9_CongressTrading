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
| `dashboard.py` | Streamlit app entry (registers pages) — *removed at cutover* |

## `src/api/` — FastAPI service (migration target)

| File | Responsibility |
|------|---------------|
| `__main__.py` | `python -m src.api` runner (uvicorn; `API_SERVER_PORT` default 8000) |
| `app.py` | `create_app()`, middleware (CORS, session), router registration, `/api/login` |
| `settings.py` | Session cookie + CORS settings (secret, name, https-only, max-age, origins) |
| `security.py` | `verify_credentials`, `login_session`, `logout_session`, `current_user`, `require_auth` |
| `query.py` | `PeriodParams`, `period_params` dep, `Slice`, `get_slice` dep (request-scoped data slice) |
| `repository.py` | Data loading/caching + prep ported from `dashboard_shared/data.py` (load_transactions, load_review_queue, load_dataset, period/lookback filters) |
| `serialize.py` | DataFrame/value → JSON-safe records (`iso_date`, `clean`, `records`) |
| `_constants.py` | Pure copy of dashboard constants (column names, etc.) |
| `_format.py` | Pure copy: percent/currency/range formatting, amount sums |
| `_sparklines.py` | Pure copy: monthly series, KPI sparklines, MoM delta |
| `routers/home.py` | `/api/home/summary` — hero, KPIs, breakdown, monthly activity, top members/tickers |

> `_constants.py`, `_format.py`, `_sparklines.py`, `repository.py` are **self-contained copies** of `dashboard_shared` pieces to avoid Streamlit imports. Keep in sync until cutover.

## `src/dashboard_pages/` — Streamlit pages (one per page, thin)

`home.py`, `members.py`, `tickers.py`, `patterns.py`, `review.py`, `raw_data.py`

## `src/dashboard_shared/` — Streamlit dashboard utilities

| File | Purpose |
|------|---------|
| `data.py` | Data loading, `@st.cache_data`, DB queries |
| `filters.py` | Sidebar filter widgets |
| `analytics.py` | Derived metrics, aggregations, pattern detection |
| `charts.py` | Plotly chart builders |
| `components.py` | Reusable UI components |
| `constants.py` | Column names, paths, SQL |
| `styles.py` | CSS/styling helpers |
| `session.py` | Session state management |
| `formatting.py` | Number/currency/date formatting |
| `dashboard_tables.py` | Table rendering helpers |
| `tables.py` | Table helpers |
| `kpi_sparklines.py` | KPI sparkline components |
| `top_bar.py` | Top bar UI |
| `auth.py` | Login gate |

## Tests (`tests/`)

`pytest` from repo root. `conftest.py` = fixtures (in-memory DB, sample DataFrames).
Coverage: api_home, dashboard_filters, dashboard_analytics, dashboard_formatting,
dashboard_kpi_sparklines, dashboard_activity_feed, dashboard_auth, dashboard_top_bar, re_resolve_tickers.

## Other

`deploy/` — VPS systemd service, deploy script, logrotate, env-merge helper.
`scripts/` — `nightly_ingest.sh`, `smoke_apis.py`, `count_empty_tickers.py`.
`bootstrap.ps1` / `deploy_local.ps1` — Windows entrypoints.
