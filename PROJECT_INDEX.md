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
| `ingest_house.py` | House PTR + FD ingest orchestrator (batch parse/persist) |
| `house_ptr_download.py` | House PTR PDF autodownload + local zip extract |
| `house_ptr_repair.py` | House PTR filing/date repair, duplicate merge, backfill |
| `re_resolve_tickers.py` | Re-resolve ticker/issuer on existing SQLite transactions |
| `ingest_senate.py` | Senate PTR ingest pipeline |
| `ingest_oge.py` | OGE Executive (278-T + 278e) ingest pipeline |
| `parse_ptr.py` | PTR PDF parsing (layout-sensitive) |
| `parse_fd.py` | Financial Disclosure PDF parsing |
| `parse_oge.py` | OGE 278-T (periodic) + 278e (annual) PDF parsing |
| `oge_source.py` | Hard-coded OGE filing registry (dataclass + `TRUMP_OGE_FILINGS`) |
| `download_house_fd.py` | Bulk download from House Clerk |
| `download_oge.py` | Conservative OGE PDF downloader (1 req/sec) |
| `house_coverage.py` | House coverage tracking |
| `ticker_lookup.py` | Ticker/CUSIP resolution (disclosure heuristics + SEC/Polygon/OpenFIGI) |
| `sec_company_tickers.py` | Cached SEC `company_tickers.json` name→ticker local lookup |
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
| `_executive_analytics.py` | Executive (OGE) summary, monthly timeline, by-owner breakdown |
| `routers/` | One router per dashboard page (home, raw, review, patterns, members, tickers, executive) |

## `frontend/` — React dashboard

| Path | Responsibility |
|------|---------------|
| `package.json` | npm scripts (`dev`, `build`, `test`, `typecheck`, `lint`) |
| `vite.config.ts` | Vite dev server, `/api` proxy → `127.0.0.1:9001` (reads `API_SERVER_PORT`), Vitest |
| `src/main.tsx` | MantineProvider + QueryClientProvider + RouterProvider |
| `src/App.tsx` | React Router config (login + dashboard pages) |
| `src/copy.ts` | Page copy strings |
| `src/styles/` | Global CSS |
| `__tests__/` | Vitest unit tests |

### `frontend/src/api/`

| File | Responsibility |
|------|---------------|
| `client.ts` | `fetch` wrapper (`credentials: "include"`) |
| `types.ts` | Shared API response types |
| `params.ts` | URL query builders for period/lookback filters |
| `queryClient.ts` | TanStack Query client |
| `auth.ts` | Login / session / logout hooks |
| `health.ts` | Health probe |
| `home.ts` | Home page query hooks |
| `raw.ts` | Raw transactions table hooks |
| `review.ts` | Review queue hooks |
| `patterns.ts` | Patterns page hooks |
| `members.ts` | Members page hooks |
| `tickers.ts` | Tickers leaderboard / list hooks |
| `tickerDrilldown.ts` | Ticker profile / price / exposure hooks |
| `executive.ts` | Executive (OGE) page hooks |
| `refresh.ts` | Data refresh status / trigger hooks |

### `frontend/src/utils/`

| File | Responsibility |
|------|---------------|
| `format.ts` | Date / currency / number formatters |
| `transactions.ts` | Sorting + display helpers for transaction tables |
| `entityLinks.ts` | Member/ticker hrefs + chart-click → navigate helpers |

### `frontend/src/charts/` — pure ECharts option builders

| File | Paired component |
|------|------------------|
| `barChart.ts` | `BarChart` |
| `rankBars.ts` | `RankBars` |
| `monthlyActivity.ts` | `MonthlyActivityChart` |
| `netTrade.ts` | `NetTradeChart` |
| `miniSparkline.ts` | `MiniSparkline` |
| `priceOverlay.ts` | `PriceOverlayChart` |
| `tickerTimeline.ts` | `TickerTimeline` |
| `callPutArea.ts` | `CallPutAreaChart` |
| `callPutRatio.ts` | `CallPutRatioChart` |
| `sectorHeatmap.ts` | `SectorHeatmapChart` |
| `cumulativeExposurePerMember.ts` | `CumulativeExposurePerMember` |

### `frontend/src/components/`

| File | Responsibility |
|------|---------------|
| `EChartsChart.tsx` | Shared SVG ECharts shell (`option`, `height`, `testId`, `onEvents`) — use for all charts |
| `ChartCard.tsx` | Titled card wrapper (optional collapse / caption) |
| `PageState.tsx` | Loading / error / empty / ready gate for pages |
| `SectionIntro.tsx` | Page kicker + title + copy |
| `KpiTile.tsx` | KPI tile (optional detail, sparkline, delta) |
| `MiniSparkline.tsx` | Tiny sparkline via `EChartsChart` |
| `BarChart.tsx` | Horizontal bar chart |
| `RankBars.tsx` | Ranked bars with optional entity click links |
| `MonthlyActivityChart.tsx` | Buy/sell/other monthly stacked bars |
| `NetTradeChart.tsx` | Net trade bars (ticker links) |
| `PriceOverlayChart.tsx` | Price series + trade markers |
| `TickerTimeline.tsx` | Scatter timeline (member or ticker axis) |
| `CallPutAreaChart.tsx` | Call/put stacked area |
| `CallPutRatioChart.tsx` | Call/put ratio line |
| `SectorHeatmapChart.tsx` | Sector × month heatmap |
| `CumulativeExposurePerMember.tsx` | Per-member cumulative exposure + legend |
| `MembersLeaderboardTable.tsx` | Members leaderboard table |
| `MemberLink.tsx` / `TickerLink.tsx` | In-app entity links |
| `MemberNamesLinks.tsx` | Comma-separated member links |
| `DirectionBadge.tsx` | Buy/sell/other badge |
| `PillStrip.tsx` | Horizontal filter/selection pills |
| `AmountRangeFilter.tsx` | Amount low/high filter control |
| `FilterContext.tsx` | Shared period/lookback slice for pages |
| `SidebarLayout.tsx` | Authenticated shell (TopBar + sidebar) |
| `SidebarFilters.tsx` | Lookback / quarters sidebar |
| `TopBar.tsx` | Nav + user menu |
| `UserMenu.tsx` | Account / logout |
| `DonateButton.tsx` | Ko-fi donate link |
| `RequireAuth.tsx` | Session gate |
| `ErrorBoundary.tsx` | React error boundary |
| `RefreshProgressPanel.tsx` / `RefreshLogPanel.tsx` | Refresh UI |
| `PageStub.tsx` | Placeholder page |

### `frontend/src/routes/`

| File | Responsibility |
|------|---------------|
| `Login.tsx` | Auth form |
| `Home.tsx` | Overview KPIs, activity, leaderboards |
| `Raw.tsx` | Filterable raw transactions table |
| `Review.tsx` | Review queue |
| `Members.tsx` | Member drilldown |
| `Tickers.tsx` | Ticker leaderboard + drilldown |
| `Patterns.tsx` | Pattern detection views |
| `Executive.tsx` | OGE Executive (278-T / 278e) |
| `NotFound.tsx` | 404 |

## Tests (`tests/`)

`pytest` from repo root. `conftest.py` = fixtures (in-memory DB, sample DataFrames).
Coverage: `test_api_*.py`, `test_re_resolve_tickers.py`.

## Other

`deploy/` — VPS systemd services (congress-api, congress-web), Caddy config, deploy script, logrotate, env-merge helper.
`scripts/` — `nightly_ingest.sh`, `smoke_apis.py`, `count_empty_tickers.py`.
`bootstrap.ps1` / `deploy_local.ps1` — Windows entrypoints.
