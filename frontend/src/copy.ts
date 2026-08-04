/** Page copy strings for the React dashboard. */
export const COPY = {
  home: {
    monthlyActivity:
      "Buy/sell counts (bars) and disclosed dollar high (line). Shaded months are often incomplete — STOCK Act filings can lag ~45 days.",
  },
  review: {
    kicker: "Review Queue",
    title: "Triage unresolved records",
    copy: "These rows still require manual confirmation or a better asset resolution. Save a ticker, accept a fuzzy match, or dismiss a row to clear the backlog.",
    recordsCard: "Records needing review",
    byReason: "By reason",
    byStatus: "By status",
    reasonCaption: "How many review-queue rows per reason code.",
    statusCaption: "How many review-queue rows per status (open, …).",
    summaryTable: "Summary",
    transactionDetail: "Full transaction detail",
    actionsCaption:
      "Save sets the ticker and marks the trade resolved. Accept keeps the current ticker. Dismiss drops the queue row without changing the trade.",
    applyToAsset: "Apply Save/Accept to all open rows with the same asset name",
  },
  members: {
    kicker: "Members",
    title: "Politician profiles",
    copy: "Pick a member from the leaderboard or use the arrows to cycle profiles — KPIs, by-ticker breakdown, committee-overlap trades, and activity for the active period slice.",
    browse: "Members leaderboard",
    profile: "Member profile",
    emptyProfile: "Pick a member from the list or use the arrows to open a profile.",
    allTrades: "All trades",
    committeeRelevant: "Committee relevant",
    byTicker: "By ticker",
    activity: "Activity over time",
    topTickers: "Top tickers by trade count",
    committeeCard: "Committee-relevant trades",
  },
  tickers: {
    kicker: "Tickers",
    title: "Stock-level congressional activity",
    copy: "Pick a symbol to see who traded it, price overlay, member timeline, and cumulative net exposure.",
    whoTraded: "Who traded this ticker",
    priceOverlay: "Price & trade overlay",
    memberTimeline: "Member timeline",
    cumulativeExposure: "Net disclosed dollars over time",
    cumulativeGuideTitle: "How to read this chart",
    cumulativeGuideLines:
      "One shared scale · each colored step line is a member · shaded band = disclosure floor–ceiling · step up = buy · step down = sell · click the legend to hide/show members",
    cumulativeGuideNote:
      "Filings report dollar ranges, not exact amounts. The line is the midpoint estimate; the band is how wide that range can be — a rough activity proxy, not holdings.",
    noPolygon: "No Polygon cache data for this ticker — run python -m src.main warm-polygon-price-cache",
  },
  patterns: {
    kicker: "Patterns",
    title: "Signals & coordination",
    copy: "Committee overlap, coordinated trades, sector flow, call/put trends, disclosure spikes, and bipartisan activity.",
    committee: "Committee relevance",
    coordinated: "Coordinated buying / selling",
    sectorHeatmap: "Sector concentration",
    sectorHeatmapCaption:
      "Trade counts by GICS sector over time. Darker cells mean more disclosures that month. Recent months may be incomplete due to filing lag.",
    callPut: "Call vs put trends",
    callPutNote: ">1 means more calls than puts that month.",
    tickerFilter: "Filter call/put chart by ticker (optional)",
    volumeSpikes: "Disclosure spikes",
    volumeCaption: "≥3 recent disclosures AND recent_per_month ≥ 2× prior_per_month",
    volumeSpikeChart: "Top spike ratios",
    bipartisan: "Bipartisan trades",
    bipartisanEmpty:
      "No bipartisan ticker overlap in this window. Try a longer lookback window, or run enrich-member-parties if party data is missing.",
  },
} as const;
