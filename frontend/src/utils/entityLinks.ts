/** Deep-link into the Members workspace for a filer name. */
export function memberHref(name: string, extraParams?: Record<string, string>): string {
  let qs = `member=${encodeURIComponent(name.trim())}`;
  if (extraParams) {
    for (const [key, value] of Object.entries(extraParams)) {
      qs += `&${encodeURIComponent(key)}=${encodeURIComponent(value)}`;
    }
  }
  return `/members?${qs}`;
}

/** Deep-link into the Tickers workspace for a symbol (optional override). */
export function tickerHref(symbol: string, override?: string): string {
  let qs = `ticker=${encodeURIComponent(symbol.trim())}`;
  const ov = (override ?? "").trim().toUpperCase();
  if (ov) qs += `&ticker_override=${encodeURIComponent(ov)}`;
  return `/tickers?${qs}`;
}

/** Split Patterns-style comma-joined member name blobs into individual names. */
export function splitMemberNames(blob: string): string[] {
  if (!blob.trim()) return [];
  return blob
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

export type EntityLinkKind = "member" | "ticker";

/**
 * Resolve an ECharts click (series bar/point or category axis label) into a
 * navigation path, or null when the click is not on a navigable entity.
 */
export function hrefFromChartClick(
  params: {
    componentType?: string;
    name?: string;
    value?: unknown;
    seriesName?: string;
  },
  kind: EntityLinkKind,
): string | null {
  let label = "";
  if (params.componentType === "yAxis" || params.componentType === "xAxis") {
    label = String(params.value ?? params.name ?? "").trim();
  } else if (params.componentType === "series") {
    // Category scatter timelines: value is [date, category, amount].
    if (Array.isArray(params.value) && typeof params.value[1] === "string") {
      label = params.value[1].trim();
    } else if (
      kind === "member" &&
      params.seriesName &&
      params.seriesName !== "__zero__"
    ) {
      // Cumulative overlay: seriesName is the member. Scatter markers set
      // params.name to the txn type ("Buy"/"Sell"), so prefer seriesName.
      label = String(params.seriesName).replace(/ · trades$/, "").trim();
    } else {
      // Category bar charts: params.name is the category label.
      label = String(params.name ?? "").trim();
      if (!label && params.seriesName && params.seriesName !== "__zero__") {
        label = String(params.seriesName).replace(/ · trades$/, "").trim();
      }
    }
  }
  if (!label) return null;
  return kind === "member" ? memberHref(label) : tickerHref(label);
}
