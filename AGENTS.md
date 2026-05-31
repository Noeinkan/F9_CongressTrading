# Agent instructions — Congress Trading

## Project

Python tracker for U.S. House and Senate public financial disclosures: raw PDFs under `data/raw/`, normalized data in SQLite under `data/db/`, optional CSV exports, and a multi-page Streamlit dashboard. Full setup, legal notes, and CSV schema: **README.md**.

## Environment

- **Python**: 3.10+
- **Interpreter**: prefer project venv `.venv\Scripts\python.exe` (Windows) — see README troubleshooting if imports fail.
- **Secrets**: `POLYGON_API_KEY`; optional `OPENFIGI_API_KEY`.
- **House PTR autodownload** (defaults in `src/config.py`): `HOUSE_PTR_AUTO_DOWNLOAD`, `HOUSE_PTR_AUTO_DOWNLOAD_MIN_YEAR`, `HOUSE_PTR_AUTO_DOWNLOAD_MAX_YEAR`, `HOUSE_PTR_DOWNLOAD_MIN_INTERVAL_SECONDS`. Be conservative with Clerk traffic; do not bulk-hammer `disclosures-clerk.house.gov`. Senate eFD has its own terms — README.

## Entrypoint

All CLI: **`python -m src.main <command>`** from repo root.

| Command | Purpose |
|--------|---------|
| `download-house-fd` | Bulk House FD zips → `data/raw/house/` (`--years`, `--overwrite`, `--zip-only`) |
| `ingest-house` | House PTR + FD pipeline |
| `ingest-senate` | Senate PTR (expects PDFs present) |
| `ingest-all` | House + Senate |
| `export-csv` | Normalized trades → `--out` (default `data/congress_trades.csv`). Optional Polygon columns: `--polygon-pnl` [`--as-of YYYY-MM-DD`] [`--polygon-pnl-cache-only`] [`--polygon-pnl-refresh`] |
| `warm-polygon-price-cache` | Prefetch Polygon daily bars into `polygon_daily_bar_cache` for tickers in `transactions` (`--as-of`, `--refresh`, `--cache-only`) |
| `export-fd-csv` | FD report CSV |
| `export-review-csv` | Review queue CSV |
| `dashboard` | Streamlit (`--server-port`, `--server-address`) |
| `refresh-dashboard` | Re-ingest, re-export, restart dashboard |

Windows bootstrap: `powershell -ExecutionPolicy Bypass -File .\bootstrap.ps1 <same-subcommand>`.

## Layout

- **`src/`** — application code (core modules below).
- **`src/dashboard_pages/`** — one file per Streamlit page (`home.py`, `members.py`, `tickers.py`, `patterns.py`, `review.py`, `raw_data.py`).
- **`src/dashboard_shared/`** — shared dashboard utilities (see Dashboard Architecture below).
- **`data/raw/house/`**, **`data/raw/senate/`** — PDFs (and zips; pipeline may extract).
- **`data/db/`** — SQLite.
- **`data/cache/`** — ticker resolution cache.
- **`tests/`** — pytest test suite; run with `pytest` from repo root.

### Core modules in `src/`

| Module | Responsibility |
|--------|---------------|
| `config.py` | Paths, env vars, constants |
| `db.py` | SQLite connection, schema init, shared queries |
| `utils.py` | Shared utilities (`normalize_key`, text helpers) |
| `main.py` | CLI entrypoint (argparse) |
| `ingest_house.py` | House PTR + FD ingest pipeline |
| `ingest_senate.py` | Senate PTR ingest pipeline |
| `parse_ptr.py` | PTR PDF parsing |
| `parse_fd.py` | Financial Disclosure PDF parsing |
| `download_house_fd.py` | Bulk download from House Clerk |
| `ticker_lookup.py` | Ticker/CUSIP resolution |
| `issuer_enrichment.py` | Issuer metadata enrichment |
| `polygon_prices.py` | Polygon.io daily bar fetching + cache |
| `export_csv.py` | CSV export logic |
| `house_coverage.py` | House coverage tracking |
| `dashboard.py` | Streamlit app entry (registers pages) |

## Dashboard Architecture

Multi-page Streamlit app. Each page in `src/dashboard_pages/` is self-contained but imports shared code from `src/dashboard_shared/`.

### `src/dashboard_shared/` modules

| Module | Purpose |
|--------|---------|
| `data.py` | Data loading, caching (`@st.cache_data`), DB queries |
| `filters.py` | Sidebar filter widgets (date, member, ticker, party, etc.) |
| `analytics.py` | Derived metrics, aggregations, pattern detection |
| `charts.py` | Plotly/Altair chart builders |
| `components.py` | Reusable UI components (cards, badges, tables) |
| `constants.py` | Column names, file paths, SQL queries |
| `styles.py` | CSS/styling helpers |
| `session.py` | Streamlit session state management |
| `formatting.py` | Number/currency/date formatting |
| `dashboard_tables.py` | Table rendering helpers |
| `kpi_sparklines.py` | KPI sparkline components |

### Conventions for dashboard code

- Data flows: `data.py` loads → filters narrow → analytics compute → charts/tables render.
- Use `@st.cache_data` for expensive queries; invalidate via `ttl` or manual `st.cache_data.clear()`.
- Filter state lives in `st.session_state`; use `session.py` helpers to read/write.
- Charts use Plotly; keep chart-building functions in `charts.py`, not inline in pages.

## Data model (high level)

SQLite holds normalized tracker tables: `members`, `filings`, `transactions`, `issuers`, `transaction_tags`, `review_queue`, `asset_resolution_cache`, `polygon_daily_bar_cache` (Polygon daily closes for optional return/PnL-style export and dashboard). Asset resolution: `exact_match` / `fuzzy_match` / `manual_review` — parser and mapping are heuristic.

## Testing

- Tests live in `tests/`; run `pytest` from repo root.
- `conftest.py` provides fixtures (in-memory DB, sample DataFrames).
- Test files cover: filters, analytics, formatting, KPI sparklines, activity feed.
- When adding dashboard features, add corresponding tests for data/logic (not Streamlit widget rendering).

## When editing code

- Prefer **small, targeted changes**; avoid unrelated refactors.
- PTR parsing depends on PDF layout — regressions are easy; align with existing patterns in `src/`.
- Match existing style and naming; do not add heavy docstrings for obvious code.
- Do not commit unnecessary large binaries; raw data policy is the user's choice — README describes paths and downloads.
- Dashboard changes: keep page files thin (orchestration only); push logic into `dashboard_shared/`.
- See `PATTERNS_ROADMAP.md` for planned pattern-detection features.
