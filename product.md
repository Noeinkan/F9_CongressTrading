# F9_CongressTrading Product Brief

## Executive Summary

F9_CongressTrading is a Python data-pipeline plus web-application that ingests U.S. public financial-disclosure documents (House Periodic Transaction Reports, Senate PTRs, OGE Executive 278-T and 278e forms) from PDFs, normalizes them into a SQLite database, resolves declared assets to stock tickers, optionally fetches daily price bars, and exposes the resulting dataset through a FastAPI JSON service and a React dashboard. A Windows-friendly CLI (`python -m src.main <command>`) drives the pipeline; a long-running API (`python -m src.api`) plus a Vite/React frontend (`frontend/`) serve the dashboard.

- CLI entrypoint: `src/main.py` (subcommands documented in `AGENTS.md`).
- API entrypoint: `src/api/__main__.py` (uvicorn on `127.0.0.1:9001` by default).
- Frontend entrypoint: `frontend/src/main.tsx` (Vite dev server, port 5173, proxies `/api/*` to the API).
- Storage: SQLite at `data/db/congress_trades.sqlite`; raw PDFs under `data/raw/{house,senate,oge}/`; ticker/issuer/price caches in SQLite tables.

## Problem it Solves

U.S. public financial disclosures (House PTRs, Senate PTRs, OGE Executive 278-T/278e forms) are published as PDFs on disparate government portals (House Clerk, Senate eFD, OGE). The data inside those PDFs is layout-fragile, assets are declared as free-text names rather than tickers, and there is no first-party API that aggregates and normalizes them. F9_CongressTrading automates acquisition, parsing, normalization, asset-to-ticker resolution, and storage so the resulting dataset can be queried, exported, and visualized as a single coherent source.

- PDF layout variability is documented as a real constraint in `README.md` ("il parser PTR resta euristico e dipende dalla struttura del PDF").
- Free-text asset names are addressed by an explicit resolution pipeline (Polygon + optional OpenFIGI fallback) producing `exact_match` / `fuzzy_match` / `manual_review` classifications.
- Three different disclosure regimes (House, Senate, Executive) are unified into one schema with a `chamber` discriminator (`'House'`, `'Senate'`, `'Executive'`).

## What it Does

- **Downloads filings**: bulk House FD zips (`download-house-fd`), House PTR PDFs (auto-download during `ingest-house` against `disclosures-clerk.house.gov`), OGE 278-T + 278e PDFs from a hard-coded registry (`download-oge`, `src/oge_source.py`), Senate eFD PTR HTML (`download-senate`, `src/download_senate_efd.py`).
- **Parses PDFs**: `src/parse_ptr.py` (PTR), `src/parse_fd.py` (Financial Disclosure), `src/parse_oge.py` (OGE 278-T periodic + 278e annual).
- **Ingests to SQLite**: `src/ingest_house.py`, `src/ingest_senate.py`, `src/ingest_oge.py` populate the normalized tables defined in `src/db.py`.
- **Resolves assets**: `src/ticker_lookup.py` and `src/issuer_enrichment.py` map declared asset names to tickers/CUSIPs via Polygon (`POLYGON_TICKER_SEARCH`, `POLYGON_TICKER_DETAILS`) and OpenFIGI (`OPENFIGI_API_URL`, `OPENFIGI_SEARCH_URL`), caching results in `asset_resolution_cache`.
- **Caches prices**: `src/polygon_prices.py` fetches Polygon daily bars into `polygon_daily_bar_cache` and Yahoo daily bars into `yahoo_daily_bar_cache`; configurable cache source via `PRICE_CACHE_SOURCE` env.
- **Exports**: `src/export_csv.py` writes a normalized CSV (`data/congress_trades.csv`); optional Polygon PnL/return columns via `--polygon-pnl`. FD and review-queue CSVs are also exposed (`export-fd-csv`, `export-review-csv`).
- **Re-resolves tickers**: `re-resolve-tickers` command reruns ticker/issuer resolution on existing SQLite rows without re-parsing PDFs.
- **Serves a dashboard**: FastAPI (`src/api/app.py`) exposes per-page routers (`home`, `raw`, `review`, `patterns`, `members`, `tickers`, `executive`, `admin`); React frontend (`frontend/`) renders KPIs, monthly timelines, member/ticker rankings, raw table with CSV export, review queue, pattern detection, and an Executive page for OGE filers/holdings.
- **Authenticates users (optional)**: signed httpOnly session cookie via Starlette `SessionMiddleware`; credentials gated by `APP_USERNAME`/`APP_PASSWORD` env vars.

## Target Users

Target users are inferred strictly from observed code behavior and documentation:

- **Data engineers / analysts** who need a normalized, queryable dataset of congressional and executive financial disclosures (CSVs, SQLite, JSON API).
- **Personal-investor / hobbyist** users who want to browse disclosures in a local dashboard (see `README.md` "Avvio locale", `bootstrap.ps1`, `dev.ps1`, dashboard `npm start` instructions).
- **Self-hosters / single VPS operators** who deploy the API + frontend behind Caddy (`deploy/congress-api.service`, `deploy/congress-web.service`, `deploy/congress.caddy`, `deploy/README.md`).
- **Researchers investigating OGE Executive disclosures specifically** (the `executive` page, `executive_holdings` table, and `TRUMP_OGE_FILINGS` registry in `src/oge_source.py` are aimed at this audience).

No code or doc identifies commercial enterprise customers, paying subscribers, or third-party API consumers.

## Inputs

- **House PTR PDFs**: downloaded by `ingest-house` from `https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{year}/{doc_id}.pdf` using metadata harvested from FD `.txt`/`.xml` files; manual fallback is "salva il PDF a mano in `data/raw/house/<Year>/<DocID>.pdf`" (README).
- **House FD bulk zips**: `download-house-fd` fetches `https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{year}FD.zip` for years `START_YEAR` (default 2022, `src/config.py`) through the current year; options `--years`, `--overwrite`, `--zip-only`.
- **Senate PTR HTML**: `download-senate` POSTs to `https://efdsearch.senate.gov/search/report/data/` (Django + DataTables JSON endpoint), then fetches each PTR view `https://efdsearch.senate.gov/search/view/ptr/{uuid}/`; defaults to running locally because Akamai blocks datacenter IPs (config: `SENATE_EFD_AUTO_DOWNLOAD=0` by default, `SENATE_EFD_DOWNLOAD_MIN_INTERVAL_SECONDS=2.0`).
- **OGE Executive PDFs**: registry in `src/oge_source.py` (`TRUMP_OGE_FILINGS`, type `OgeFiling`); URLs under `https://extapps2.oge.gov/201/Presiden.nsf/`; downloaded at `OGE_DOWNLOAD_MIN_INTERVAL_SECONDS=1.0`.
- **Local PDFs**: pipeline recursively reads `.pdf` files under `data/raw/house/`, `data/raw/senate/`, `data/raw/oge/`; `.zip` archives are auto-extracted.
- **Polygon API**: `POLYGON_API_KEY` env var (`src/config.py` constants `POLYGON_TICKER_SEARCH`, `POLYGON_TICKER_DETAILS`, `POLYGON_AGGS_DAY`).
- **OpenFIGI API**: optional `OPENFIGI_API_KEY` (`OPENFIGI_API_URL`, `OPENFIGI_SEARCH_URL`); used as a fallback for ticker/CUSIP resolution.
- **Yahoo Finance** (price bars, optional): no API key; used when `PRICE_CACHE_SOURCE=yahoo` (default).
- **Optional credentials for VPS deployments**: `APP_USERNAME`, `APP_PASSWORD`, `APP_SESSION_SECRET`, `APP_SESSION_COOKIE`, `APP_SESSION_HTTPS_ONLY`, `APP_SESSION_MAX_AGE`, `APP_CORS_ORIGINS`.
- **Optional tuning flags**: `HOUSE_PTR_AUTO_DOWNLOAD` (default on), `HOUSE_PTR_AUTO_DOWNLOAD_MIN_YEAR` (default 2023), `HOUSE_PTR_AUTO_DOWNLOAD_MAX_YEAR`, `HOUSE_PTR_DOWNLOAD_MIN_INTERVAL_SECONDS` (default 0.2s), `HOUSE_INGEST_SKIP_EXTERNAL_ASSET_LOOKUP`, `HOUSE_INGEST_FORCE_REPARSE_PDFS`, `CONGRESS_RE_RESOLVE_NO_KEY_OK`, `PRICE_CACHE_PARALLEL_WORKERS`.

## Outputs

- **SQLite database** at `data/db/congress_trades.sqlite` containing normalized tables defined in `src/db.py`:
  - `members` (`full_name`, `normalized_name`, `chamber`, `state`, `district`, `party`)
  - `filings` (`member_id`, `chamber`, `filing_type`, `filing_date`, `doc_id`, `source_url`, `raw_document_path`, `source_hash`)
  - `transactions` (`filing_id`, `issuer_id`, `transaction_date`, `owner_type`, `asset_name_raw`, `asset_name_normalized`, `asset_type`, `ticker`, `cusip_or_figi`, `transaction_type`, `amount_low`, `amount_high`, `amount_range_raw`, `confidence_score`, `review_status`, `source_page`, `source_row`, `source_hash`)
  - `issuers` (`issuer_name`, `ticker`, `sector`, `industry`, `asset_type`)
  - `transaction_tags`, `review_queue`, `asset_resolution_cache`, `files_ingested`, `ticker_cache`, `trades` (legacy), `fd_filings` (legacy)
  - `polygon_daily_bar_cache`, `yahoo_daily_bar_cache`, `ticker_details_cache` (Polygon metadata cache)
  - `executive_holdings` (OGE 278e annual-report snapshot of holdings, separate from periodic transactions)
- **CSV exports**:
  - `data/congress_trades.csv` (default, configurable via `--out`) — columns include `member`, `chamber`, `filing_type`, `filing_date`, `transaction_date`, `owner_type`, `asset_name_raw`, `asset_name_normalized`, `asset_type`, `issuer_name`, `ticker`, `transaction_type`, `amount_low`, `amount_high`, `amount_range_raw`, `confidence_score`, `review_status`, `source_url`, `raw_document_path`. Optional Polygon columns are appended when `--polygon-pnl` is set.
  - `data/fd_filings.csv` (`export-fd-csv`)
  - `data/review_queue.csv` (`export-review-csv`)
- **FastAPI JSON endpoints** mounted under `/api/`:
  - `/api/health`, `/api/login`, `/api/logout`, `/api/me`, `/api/session` (auth/meta)
  - Routers: `home`, `raw`, `review`, `patterns`, `members`, `tickers`, `executive`, `admin`
- **React dashboard** pages: Home (KPIs + monthly timeline), Raw (server-side sort/filter, CSV download), Review, Patterns, Members, Tickers, Executive (OGE filers/filings/transactions/holdings), plus `/login`.
- **Deployment artifacts** for Linux VPS: `deploy/congress-api.service`, `deploy/congress-web.service`, `deploy/congress.caddy`, `deploy/congress-watchdog.{service,timer}`, `deploy/logrotate-f9-congress-trading`, `deploy/bootstrap_services.sh`.

## Benefits & Value Proposition

- **Single normalized schema** across House, Senate, and OGE disclosures (`chamber` discriminator), so all three sources are queryable through the same SQLite tables and API surface.
- **Idempotent ingestion**: `files_ingested` table tracks SHA-256s; `INSERT OR IGNORE` / `ON CONFLICT` upserts in `db.py` make repeated runs safe.
- **Asset-to-ticker resolution with confidence tiers** (`exact_match` ≥ 0.98, `fuzzy_match` < 0.98 with non-empty ticker, `manual_review` otherwise) persisted in `asset_resolution_cache`.
- **Tunable throttling defaults** that respect government site limits: `HOUSE_PTR_DOWNLOAD_MIN_INTERVAL_SECONDS=0.2`, `OGE_DOWNLOAD_MIN_INTERVAL_SECONDS=1.0`, `SENATE_EFD_DOWNLOAD_MIN_INTERVAL_SECONDS=2.0`. README explicitly warns: "non schedulare richieste massicce o troppo frequenti".
- **Optional Polygon daily-bar enrichment** (`polygon_daily_bar_cache`, `export-csv --polygon-pnl`) allows return-style analytics without re-hitting the API on every export.
- **Local-first dashboard** via a SQLite-backed API, with no SaaS dependency; optional auth gate for VPS exposure (`APP_USERNAME`/`APP_PASSWORD`).
- **Dual-source price cache** (`yahoo_daily_bar_cache`, `polygon_daily_bar_cache`) selectable at runtime via `PRICE_CACHE_SOURCE`.
- **Triage workflow**: `review_queue` table + `export-review-csv` + a dedicated `Review` dashboard page surface ambiguous rows without blocking the main dataset.
- **Coverage audit**: `verify-house-coverage` prints a freshness report (`house_coverage_max_filing_lag_days` default 75).

## Typical Workflow

A typical end-to-end run, as encoded in the CLI subcommands:

1. `python -m src.main download-house-fd` — bulk-download House FD metadata zips into `data/raw/house/`.
2. `python -m src.main ingest-house` — extracts zips, autodownloads PTR PDFs from the Clerk (subject to throttling/env flags), parses PDFs, upserts `members`, `filings`, `transactions`, `issuers`, populates `asset_resolution_cache` via Polygon/OpenFIGI, and writes fuzzy-match rows into `review_queue`.
3. `python -m src.main download-senate --since 2023` — scrapes Senate eFD PTRs into `data/raw/senate/` (run locally; default off during `ingest-senate`).
4. `python -m src.main ingest-senate` — parses Senate PTR HTML/PDFs and writes to the same normalized tables (`chamber='Senate'`).
5. `python -m src.main download-oge [--filer "Donald J. Trump"] [--overwrite]` — downloads OGE 278-T/278e PDFs from the hard-coded `TRUMP_OGE_FILINGS` registry.
6. `python -m src.main ingest-oge` — 278-T rows go to `transactions`, 278e rows go to `executive_holdings` (`chamber='Executive'`).
7. `python -m src.main warm-polygon-price-cache` — prefetches Polygon daily bars into `polygon_daily_bar_cache` (or `warm-yahoo-price-cache` / `warm-price-cache` for the dual-source mode).
8. `python -m src.main export-csv --out data/congress_trades.csv [--polygon-pnl --as-of YYYY-MM-DD]` — produces the normalized CSV (optionally with price columns).
9. `python -m src.main export-review-csv --out data/review_queue.csv` — exports the manual-review queue.
10. `python -m src.api` + `cd frontend && npm run dev` — serve the dashboard locally (API on `127.0.0.1:9001`, Vite on `:5173`).
11. Windows bootstrap shortcut: `powershell -ExecutionPolicy Bypass -File .\bootstrap.ps1 ingest-all` (or any subcommand).

For deployment, the documented flow is: build frontend (`npm ci && npm run build`), copy to VPS, run `deploy/bootstrap_services.sh` (systemd + Caddy), expose on port 80.

## Technical Foundation

- **Language**: Python 3.10+ (`README.md`, `AGENTS.md`).
- **CLI**: `argparse` subparsers in `src/main.py`; Windows entrypoint `bootstrap.ps1`.
- **Storage**: SQLite via stdlib `sqlite3`, WAL journal mode, foreign keys enabled (`src/db.py: get_connection`, `init_db`).
- **PDF parsing**: layout-sensitive heuristics in `src/parse_ptr.py`, `src/parse_fd.py`, `src/parse_oge.py` (README: "il parser PTR resta euristico e dipende dalla struttura del PDF").
- **Networking**: `requests` for House FD; `curl_cffi` impersonation for Senate eFD (Akamai TLS fingerprinting, `SENATE_EFD_IMPERSONATE` env, default `chrome`); conservative rate-limiters (`src/config.py`).
- **External APIs**: Polygon.io (`POLYGON_TICKER_SEARCH`, `POLYGON_TICKER_DETAILS`, `POLYGON_AGGS_DAY`), OpenFIGI (`OPENFIGI_API_URL`, `OPENFIGI_SEARCH_URL`), Yahoo Finance daily bars (used by `polygon_prices.py` when `PRICE_CACHE_SOURCE=yahoo`).
- **API**: FastAPI + uvicorn, Starlette `SessionMiddleware` (signed httpOnly cookie), `CORSMiddleware`, Pydantic models; `src/api/repository.py` for data loading, `src/api/_*_analytics.py` for page analytics, `src/api/routers/` for thin per-page routers, `src/api/security.py` for credentials.
- **Frontend**: React 18, Vite 6, Mantine 8, TanStack Query 5, TanStack Table 8, ECharts 5, react-router-dom 6, TypeScript 5; Vitest for unit tests; ESLint with `@typescript-eslint`.
- **Frontend dev proxy**: `frontend/vite.config.ts` proxies `/api/*` to `127.0.0.1:9001` (reads `API_SERVER_PORT`).
- **Tests**: pytest (`tests/test_api_*.py`, `tests/test_re_resolve_tickers.py`, `tests/test_oge_ingest.py`, `tests/test_senate_efd.py`, `tests/test_utils_*.py`, `tests/test_yahoo_*`, `tests/test_no_streamlit_imports.py`); `tests/conftest.py` provides in-memory DB and sample-DataFrame fixtures. Frontend tests via `cd frontend && npm test`.
- **Configuration**: `src/config.py` (paths, env vars, URL constants, helpers), plus repo-root `.env` loaded via `python-dotenv` if installed.
- **Deployment**: Caddy reverse proxy, systemd services, logrotate, optional watchdog timer (`deploy/`).
- **Clean-boundary rule** (`CLAUDE.md`): no Streamlit imports anywhere under `src/api/` (enforced by `tests/test_no_streamlit_imports.py`).

## Current Limitations & Boundaries

- **Parser is heuristic and layout-sensitive** for PTR/FD/OGE PDFs (README "Limiti correnti"; `AGENTS.md`: "PTR parsing depends on PDF layout — regressions are easy").
- **Ticker resolution is bounded by disclosure-text quality** (README: "la risoluzione degli asset distingue ora exact match, fuzzy match e manual review, ma resta limitata dalla qualita dei nomi dichiarati nei PDF").
- **Fuzzy matches export a ticker but stay in the review queue; `manual_review` rows have no ticker** until corrected downstream (README).
- **`download-house-fd` and House PTR autodownload** can trigger hundreds-to-thousands of Clerk requests; README recommends `HOUSE_PTR_AUTO_DOWNLOAD_MAX_YEAR` or `HOUSE_PTR_AUTO_DOWNLOAD=0` to throttle.
- **Senate eFD scraping is intentionally local-only by default** because Akamai blocks datacenter IPs (`SENATE_EFD_AUTO_DOWNLOAD=0` default, `SENATE_EFD_DOWNLOAD_MIN_INTERVAL_SECONDS=2.0`); requires terms acceptance.
- **OGE registry is hard-coded** (`TRUMP_OGE_FILINGS` in `src/oge_source.py`); adding a new filer is a code change, and 404s fail loud (no auto-rescrape).
- **No alerting / notification system** (README: "non esiste ancora un sistema di alert; la dashboard React e il primo layer di analisi sopra il backend normalizzato").
- **`re-resolve-tickers` requires** `POLYGON_API_KEY` or `OPENFIGI_API_KEY` (opt-out via `CONGRESS_RE_RESOLVE_NO_KEY_OK=1`).
- **Polygon daily-bar coverage depends on tickers being equities**; the post-run log warns "probabilmente ticker non quotati o asset non-equity".
- **HTTP-only deployments expose credentials in cleartext** (README: "su HTTP le credenziali viaggiano in chiaro").
- **`data/raw/`, `data/db/`, `data/cache/`, `data/*.csv` are gitignored** — local recreation is required (README, `.gitignore`).
- **Legacy tables retained** (`trades`, `fd_filings`, `ticker_cache`) alongside the normalized schema (README "Stato attuale").
- **Frontend OGE filer coverage is registry-driven**; only filers added to `TRUMP_OGE_FILINGS` appear in the Executive page.
- **No payment, billing, subscription, SSO, role-based-access, multi-tenant, or quota system** is implemented anywhere in the codebase.

## Extensibility & Integration Points

- **Adding a new OGE filer**: append an `OgeFiling` entry to `TRUMP_OGE_FILINGS` in `src/oge_source.py`; the `download-oge` and `ingest-oge` commands pick it up automatically (--filer filter supported).
- **Adding a new CLI subcommand**: register a new subparser in `build_parser()` and a handler branch in `main()` in `src/main.py`.
- **Adding a new SQLite table**: extend `init_db()` in `src/db.py`; the function is idempotent and uses `CREATE TABLE IF NOT EXISTS` plus `_ensure_columns` for additive migrations.
- **Adding a new dashboard page**: add a router in `src/api/routers/`, register it in `src/api/app.py:create_app()`, add analytics helpers under `src/api/_*_analytics.py`, add a route component in `frontend/src/routes/`, and wire it in `frontend/src/App.tsx` inside the `RequireAuth` → `SidebarLayout` children.
- **Adding a new asset-resolution source**: extend `src/ticker_lookup.py` / `src/issuer_enrichment.py` and persist the result via `upsert_asset_resolution` in `src/db.py`.
- **Adding a new price provider**: implement a fetcher in `src/polygon_prices.py` (e.g., the existing Yahoo path is a template), and add a corresponding SQLite cache table in `init_db()`; toggle via `PRICE_CACHE_SOURCE`.
- **Adding a new export format**: extend `src/export_csv.py` (`export_csv`, `export_fd_csv`, `export_review_csv` are the existing templates).
- **Frontend hooks**: each page calls a TanStack Query hook in `frontend/src/api/`; new endpoints map 1:1 to new hooks.
- **Deployment**: VPS bring-up uses `deploy/bootstrap_services.sh`, `deploy/congress.caddy`, `deploy/congress-api.service`, `deploy/congress-web.service`; `deploy/README.md` documents the path from `main` push to running services.
- **Authentication**: gated by `APP_PASSWORD` (presence enables the login gate); session secret, cookie name, https-only flag, max-age, and CORS origins are env-configurable via `APP_SESSION_SECRET`, `APP_SESSION_COOKIE`, `APP_SESSION_HTTPS_ONLY`, `APP_SESSION_MAX_AGE`, `APP_CORS_ORIGINS`.
- **Scheduled ingest**: `scripts/nightly_ingest.sh` (referenced in `PROJECT_INDEX.md`).
- **Smoke tests / diagnostics**: `scripts/smoke_apis.py` (Polygon + OpenFIGI key check), `scripts/count_empty_tickers.py` (empty-ticker diagnostics), `scripts/clean-ports.ps1`, `scripts/dev-api.js`, `scripts/check-venv.js`.
- **Cross-cutting convention** (CLAUDE.md): API routers stay thin; analytics and data-access logic live in `repository.py`/`query.py`/`_*_analytics.py`.