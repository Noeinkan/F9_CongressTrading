# Agent instructions — Congress Trading

## Project

Python tracker for U.S. House and Senate public financial disclosures: raw PDFs under `data/raw/`, normalized data in SQLite under `data/db/`, optional CSV exports and a Streamlit dashboard. Full setup, legal notes, and CSV schema: **README.md**.

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

- **`src/`** — application code (`config.py`, ingest, parse, db, dashboard helpers).
- **`data/raw/house/`**, **`data/raw/senate/`** — PDFs (and zips; pipeline may extract).
- **`data/db/`** — SQLite.
- **`data/cache/`** — ticker resolution cache.

## Data model (high level)

SQLite holds legacy tables plus normalized tracker tables: `members`, `filings`, `transactions`, `issuers`, `transaction_tags`, `review_queue`, `asset_resolution_cache`, `polygon_daily_bar_cache` (Polygon daily closes for optional return/PnL-style export and dashboard). Asset resolution: `exact_match` / `fuzzy_match` / `manual_review` — parser and mapping are heuristic.

## When editing code

- Prefer **small, targeted changes**; avoid unrelated refactors.
- PTR parsing depends on PDF layout — regressions are easy; align with existing patterns in `src/`.
- Match existing style and naming; do not add heavy docstrings for obvious code.
- Do not commit unnecessary large binaries; raw data policy is the user’s choice — README describes paths and downloads.
