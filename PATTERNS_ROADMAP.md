# Patterns Page — Feature Roadmap

Potential additions to the Patterns dashboard page, prioritised by effort vs. impact.

---

## 1. Late Filing / Disclosure Delay Analysis

**Effort:** Low | **Impact:** High

- Calculate days between trade date and disclosure date for each transaction.
- Flag late filers (>45 days, per STOCK Act requirement).
- Rank members by average delay; highlight repeat offenders.
- Correlate late filings with trade performance — did the stock move significantly before the filing went public?
- Late disclosures on winning trades are particularly suspicious.

**Data needed:** `transaction_date` and `disclosure_date` (likely already in the DB).

---

## 2. Post-Trade Return Performance ("Copycat Returns")

**Effort:** Medium | **Impact:** High

- Simulated portfolio performance if you had mimicked each member's disclosed trades.
- Leaderboard of members by hypothetical return (30/60/90/365-day post-trade).
- Highlight the "best performing" members whose buys consistently outperform the market.
- Compare against S&P 500 benchmark for the same period.

**Data needed:** Polygon daily bar cache (already available).

---

## 3. Behavioral Anomaly Scoring

**Effort:** Medium | **Impact:** High

- Build a behavioural baseline per member: normal trading frequency, average size, typical sectors.
- Flag deviations: e.g. a member who usually trades 2×/month suddenly doing 15 trades in a week; a member who never trades tech suddenly buying NVDA heavily.
- Display a simple "anomaly score" badge (z-score relative to that member's history).
- Inspired by Signal Congress's 0-100 conviction scoring across five dimensions.

---

## 4. Sector Concentration Heat Map

**Effort:** Low–Medium | **Impact:** Medium

- Aggregate trades by GICS sector over time — show where congressional money is flowing.
- Sector rotation chart: when Congress collectively pivots from one sector to another.
- Visualise as a heat map or stacked area chart.
- Surfaces "the whole chamber is suddenly buying defence stocks" patterns that per-ticker views miss.

**Data needed:** Ticker-to-sector mapping (could use Polygon or a static lookup).

---

## 5. Committee Relevance Scoring

**Effort:** Medium–High | **Impact:** High

- Map each member to their committee assignments (Armed Services, Energy & Commerce, Finance, etc.).
- Tag tickers by sector/industry.
- Flag trades where the member sits on a committee with jurisdiction over the company's sector.
- Show a "committee overlap" score or badge on trades.
- Academic research calls these "enterprising trades" — the strongest statistical signal for abnormal returns.

**Data needed:** Committee membership data (static or from an API like ProPublica Congress API); ticker-to-sector mapping.

---

## 6. Pre-Event Timing Patterns

**Effort:** High | **Impact:** Very High

- Cluster trades relative to known catalysts: earnings dates, FDA decisions, major contract awards, legislative markups.
- "Trades before news" detector: trades that precede a large price move (>5-10% within 30 days).
- Chart of post-trade return distribution — are certain members' trades systematically followed by positive price movement?
- Approximate with Polygon price cache: compare 30/60/90-day returns after each trade to the S&P 500 benchmark.

**Data needed:** External event calendar (earnings, FDA, legislative markups); Polygon prices.

---

## 7. Network / Cluster Visualisation

**Effort:** Medium | **Impact:** Medium

- Network graph showing which members trade together frequently (nodes = members, edges = shared tickers within time windows).
- Highlight trading cliques — small groups that consistently trade the same stocks.
- Filter by party, committee, state to see if clustering is political, informational, or coincidental.
- Goes beyond the existing "coordinated trades" table with a visual representation.

**Data needed:** Existing transaction data; a graph library (e.g. `networkx` + Streamlit component or Altair force layout).

---

## 8. Cross-Source Corroboration

**Effort:** Very High | **Impact:** Very High

- Enrich congressional trades with government contract awards (USASpending.gov).
- Lobbying disclosures — company lobbies a member's committee, then the member trades it.
- SEC Form 4 insider filings — corporate insiders buying/selling at the same time as Congress members.
- Simpler first version: "tickers where both Congress members AND corporate insiders are buying simultaneously."

**Data needed:** New external data sources (USASpending API, SEC EDGAR, lobbying disclosures).

---

## References

- [Signal Congress](https://www.signalcongress.com/) — anomaly scoring, ARIA briefs, 8 corroboration sources
- [TraderCongress](https://tradercongress.com/) — 6 integrated data sources in one dashboard
- [CongressFlow](https://congressflow.com/analysis/late-filers) — late filer analysis and delay tracking
- [Kapitol.ai](https://kapitol.ai/stock-act) — STOCK Act explainer and enforcement gaps
- [Kadoa Congress Trading Monitor](https://github.com/kadoa-org/congress-trading-monitor) — open-source dashboard with return overlays
- Springer (2025) — "Inside the Beltway: Senator Trading and Legislative Gains" (enterprising trades methodology)
- StockActTrades.com (2026) — forensic analysis of Q1 2026 legislative arbitrage patterns
