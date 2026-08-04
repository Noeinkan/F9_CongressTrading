import type { TickerCumulativeExposureRow } from "@/api/types";

// Per-transaction-type colors (kept consistent with the rest of the dashboard:
// tickerTimeline.ts / priceOverlay.ts).
const TYPE_COLORS: Record<string, string> = {
  Buy: "#15803d",
  Sell: "#be123c",
  "Sell (partial)": "#c2410c",
  Exchange: "#1d4ed8",
  Unknown: "#64748b",
};

// Per-member accent palette — one hue per line on the shared canvas.
const MEMBER_PALETTE = [
  "#0ea5e9", // sky
  "#f59e0b", // amber
  "#10b981", // emerald
  "#a855f7", // violet
  "#ef4444", // red
  "#14b8a6", // teal
  "#f97316", // orange
  "#6366f1", // indigo
  "#84cc16", // lime
  "#ec4899", // pink
  "#06b6d4", // cyan
  "#eab308", // yellow
  "#8b5cf6", // purple
  "#22c55e", // green
  "#0f766e", // dark teal
  "#dc2626", // dark red
];

function memberColor(index: number): string {
  return MEMBER_PALETTE[index % MEMBER_PALETTE.length] ?? "#94a3b8";
}

/** Collapse near-equal floor/ceiling (matches backend `_RANGE_EPS`). */
const RANGE_EPS = 0.5;

function hasWideRange(lo: number | undefined, hi: number | undefined): boolean {
  return typeof lo === "number" && typeof hi === "number" && Math.abs(hi - lo) > RANGE_EPS;
}

function compactCurrency(v: number): string {
  if (v === 0) return "$0";
  const abs = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (abs >= 1_000_000) return `${sign}$${(abs / 1_000_000).toFixed(abs >= 10_000_000 ? 0 : 1)}M`;
  if (abs >= 1_000) return `${sign}$${Math.round(abs / 1_000)}K`;
  return `${sign}$${abs}`;
}

// Format the x-axis time tick as a short, scannable date. ECharts' default for
// "time" axes is "yyyy-MM-dd" which is too dense to read at the widths we have.
function formatXDate(value: number): string {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "";
  // Prefer local calendar components so UTC midnight epoch ms does not shift
  // the month label west of UTC.
  return d.toLocaleDateString("en-US", { month: "short", year: "numeric", timeZone: "UTC" });
}

// Pick a "nice" round axis domain that contains [dataMin, dataMax] and snaps
// to a clean tick interval. The result also covers at least the first
// round-multiple above dataMax and below dataMin so we get whole-number
// ticks (e.g. -$30K, -$20K, -$10K, $0, $10K) instead of $8,371.
function computeSharedDomain(dataMin: number, dataMax: number): {
  min: number;
  max: number;
  interval: number;
} {
  // Always include 0 — buys and sells above/below it are the whole point of
  // the chart.
  const lo = Math.min(0, dataMin);
  const hi = Math.max(0, dataMax);

  // Round magnitude up to the next 1, 2, 2.5, 5 × 10^k to get a clean tick
  // interval. We aim for ~4–6 ticks across the range.
  const range = Math.max(1, hi - lo);
  const targetTicks = 5;
  const roughInterval = range / targetTicks;
  const magnitude = Math.pow(10, Math.floor(Math.log10(roughInterval)));
  const normalized = roughInterval / magnitude;
  let niceInterval: number;
  if (normalized < 1.5) niceInterval = 1 * magnitude;
  else if (normalized < 3) niceInterval = 2 * magnitude;
  else if (normalized < 7) niceInterval = 5 * magnitude;
  else niceInterval = 10 * magnitude;

  const niceMin = Math.floor(lo / niceInterval) * niceInterval;
  const niceMax = Math.ceil(hi / niceInterval) * niceInterval;

  return { min: niceMin, max: niceMax, interval: niceInterval };
}

export type CumulativeExposurePerMemberMeta = {
  members: string[];
  memberColors: string[];
  typeColors: Record<string, string>;
  types: string[];
};

/** Fixed chart height — single shared canvas, not one panel per member. */
export const CUMULATIVE_EXPOSURE_CHART_HEIGHT = 480;

export function buildCumulativeExposurePerMemberOption(
  rows: TickerCumulativeExposureRow[],
  members: string[],
): Record<string, unknown> | null {
  if (!rows.length || !members.length) return null;

  // Largest absolute net first so legend + default visibility emphasize
  // the most consequential members.
  const memberRank = new Map<string, number>();
  members.forEach((m) => {
    const memberRows = rows.filter((r) => r.member === m);
    const lastNet = memberRows[memberRows.length - 1]?.cumulative_net ?? 0;
    memberRank.set(m, Math.abs(lastNet));
  });
  const orderedMembers = [...members].sort((a, b) => {
    const ra = memberRank.get(a) ?? 0;
    const rb = memberRank.get(b) ?? 0;
    if (rb !== ra) return rb - ra;
    return a.localeCompare(b);
  });

  const memberColorMap: Record<string, string> = {};
  orderedMembers.forEach((m, i) => {
    memberColorMap[m] = memberColor(i);
  });

  const firstDate = rows.reduce(
    (acc, r) => (acc == null || r.transaction_date < acc ? r.transaction_date : acc),
    null as string | null,
  );
  const lastDate = rows.reduce(
    (acc, r) => (acc == null || r.transaction_date > acc ? r.transaction_date : acc),
    null as string | null,
  );

  const dataMin = rows.reduce(
    (acc, r) => Math.min(acc, r.cumulative_net, r.cumulative_low),
    Number.POSITIVE_INFINITY,
  );
  const dataMax = rows.reduce(
    (acc, r) => Math.max(acc, r.cumulative_net, r.cumulative_high),
    Number.NEGATIVE_INFINITY,
  );
  const sharedYDomain = computeSharedDomain(dataMin, dataMax);

  const series: Record<string, unknown>[] = [];

  // One $0 reference for the whole canvas.
  series.push({
    type: "line",
    name: "__zero__",
    data: [],
    silent: true,
    showSymbol: false,
    legendHoverLink: false,
    tooltip: { show: false },
    markLine: {
      symbol: "none",
      silent: true,
      label: {
        show: true,
        position: "insideEndTop",
        color: "#64748b",
        fontSize: 11,
        fontWeight: 600,
        formatter: "$0",
      },
      lineStyle: { color: "#94a3b8", type: "dashed", width: 1.25 },
      data: [{ yAxis: 0 }],
    },
  });

  orderedMembers.forEach((member, i) => {
    const accent = memberColorMap[member]!;
    const memberRows = rows
      .filter((r) => r.member === member)
      .sort((a, b) => (a.transaction_date < b.transaction_date ? -1 : 1));
    const lineData = memberRows.map((r) => [r.transaction_date, r.cumulative_net]);
    const last = memberRows[memberRows.length - 1];

    // Uncertainty band: stacked stepped areas. Same `name` as the median
    // line so legend clicks hide/show the whole member (band + line + dots).
    const hasBand = memberRows.some((r) => hasWideRange(r.cumulative_low, r.cumulative_high));
    if (hasBand) {
      const lowData = memberRows.map((r) => [r.transaction_date, r.cumulative_low]);
      const bandHeight = memberRows.map((r) => [
        r.transaction_date,
        Math.max(0, r.cumulative_high - r.cumulative_low),
      ]);
      series.push({
        name: member,
        type: "line",
        step: "end",
        data: lowData,
        showSymbol: false,
        symbol: "none",
        lineStyle: { opacity: 0, width: 0 },
        areaStyle: { opacity: 0 },
        stack: `band-${i}`,
        silent: true,
        tooltip: { show: false },
        legendHoverLink: false,
        z: 1,
        animationDuration: 250,
      });
      series.push({
        name: member,
        type: "line",
        step: "end",
        data: bandHeight,
        showSymbol: false,
        symbol: "none",
        lineStyle: { opacity: 0, width: 0 },
        areaStyle: { color: `${accent}40` },
        stack: `band-${i}`,
        silent: true,
        tooltip: { show: false },
        legendHoverLink: false,
        z: 1,
        animationDuration: 250,
      });
    }

    // Stepped cumulative median — primary series (drives legend color).
    series.push({
      name: member,
      type: "line",
      step: "end",
      data: lineData,
      showSymbol: false,
      lineStyle: { color: accent, width: 2.25, opacity: 0.95 },
      itemStyle: { color: accent },
      z: 2,
      animationDuration: 250,
      emphasis: { focus: "series", lineStyle: { width: 3.5 } },
      endLabel: last
        ? {
            show: true,
            formatter: () => last.cumulative_label ?? compactCurrency(last.cumulative_net),
            color: accent,
            fontSize: 12,
            fontWeight: 700,
            backgroundColor: "rgba(255,255,255,0.96)",
            borderColor: accent,
            borderWidth: 1.5,
            borderRadius: 4,
            padding: [4, 8],
            distance: 10,
          }
        : undefined,
    });

    // Per-transaction markers colored by txn type.
    if (memberRows.length) {
      const markerData = memberRows.map((r) => ({
        name: r.txn_type_label ?? "Trade",
        value: [r.transaction_date, r.cumulative_net],
        cumulative_low: r.cumulative_low,
        cumulative_high: r.cumulative_high,
        itemStyle: {
          color: TYPE_COLORS[r.txn_type_label ?? "Unknown"] ?? "#64748b",
          borderColor: "#ffffff",
          borderWidth: 1.5,
        },
        symbol: "circle",
        symbolSize: 7,
      }));
      series.push({
        name: member,
        type: "scatter",
        data: markerData,
        symbolSize: 7,
        z: 3,
        itemStyle: { borderColor: "#ffffff", borderWidth: 1.5 },
        emphasis: { scale: 1.4, focus: "series" },
        legendHoverLink: false,
        tooltip: { show: true },
      });
    }
  });

  // Legend room scales with member count (scrollable row(s) at top).
  const legendRows = Math.min(3, Math.ceil(orderedMembers.length / 6));
  const legendTopPad = 8 + legendRows * 22;

  return {
    grid: {
      left: 64,
      right: 168,
      top: legendTopPad + 8,
      bottom: 52,
      containLabel: false,
    },
    legend: {
      type: "scroll",
      orient: "horizontal",
      top: 4,
      left: 8,
      right: 8,
      itemWidth: 14,
      itemHeight: 10,
      itemGap: 14,
      selectedMode: true,
      textStyle: {
        fontSize: 12,
        fontWeight: 600,
        color: "#0f172a",
      },
      pageIconColor: "#334155",
      pageTextStyle: { color: "#64748b", fontSize: 11 },
      data: orderedMembers.map((m) => ({
        name: m,
        itemStyle: { color: memberColorMap[m] },
      })),
    },
    xAxis: {
      type: "time",
      min: firstDate ?? undefined,
      max: lastDate ?? undefined,
      name: "Transaction date",
      nameLocation: "middle",
      nameGap: 28,
      nameTextStyle: {
        color: "#0f172a",
        fontSize: 12,
        fontWeight: 600,
      },
      axisLabel: {
        fontSize: 12,
        color: "#334155",
        fontWeight: 500,
        hideOverlap: true,
        formatter: (v: number) => formatXDate(v),
      },
      axisLine: { lineStyle: { color: "#94a3b8" } },
      axisTick: { show: true },
      splitLine: { show: false },
    },
    yAxis: {
      type: "value",
      min: sharedYDomain.min,
      max: sharedYDomain.max,
      interval: sharedYDomain.interval,
      axisLabel: {
        fontSize: 12,
        color: "#0f172a",
        fontWeight: 600,
        formatter: (v: number) => compactCurrency(v),
        hideOverlap: true,
      },
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: {
        show: true,
        lineStyle: { color: "#e2e8f0", type: "solid" },
      },
    },
    series,
    tooltip: {
      trigger: "item",
      backgroundColor: "rgba(15, 23, 42, 0.95)",
      borderColor: "transparent",
      textStyle: { color: "#f8fafc", fontSize: 12 },
      extraCssText: "box-shadow: 0 4px 14px rgba(15, 23, 42, 0.2); border-radius: 6px;",
      formatter: (params: {
        seriesName?: string;
        name?: string;
        value: [string, number] | number;
        data?: {
          name?: string;
          value?: [string, number];
          cumulative_low?: number;
          cumulative_high?: number;
        };
        color?: string;
      }) => {
        const date =
          (Array.isArray(params.value) ? params.value[0] : params.data?.value?.[0]) ??
          params.name ??
          "";
        const net = Array.isArray(params.value)
          ? params.value[1]
          : (params.data?.value?.[1] ?? 0);
        const member = params.seriesName ?? "";
        if (member === "__zero__") return "";
        const type = params.data?.name ?? "";
        const typeColor = TYPE_COLORS[type] ?? "#94a3b8";
        const lo = params.data?.cumulative_low;
        const hi = params.data?.cumulative_high;
        const netLine =
          typeof lo === "number" && typeof hi === "number" && hasWideRange(lo, hi)
            ? `~${compactCurrency(net)} median<br/><span style="opacity:0.85;font-weight:400;">range ${compactCurrency(lo)} – ${compactCurrency(hi)}</span>`
            : `${compactCurrency(net)} net`;
        const typeBlock = type
          ? `<div style="display:flex;align-items:center;gap:6px;">
            <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${typeColor};"></span>
            <span>${type}</span>
          </div>`
          : "";
        return `
          <div style="font-weight:600;margin-bottom:2px;">${member}</div>
          <div style="opacity:0.8;font-size:11px;margin-bottom:4px;">${date}</div>
          ${typeBlock}
          <div style="margin-top:4px;font-weight:600;">${netLine}</div>
        `;
      },
    },
    // Hide overlapping end labels when many members share an endpoint.
    labelLayout: { hideOverlap: true },
    animationDuration: 400,
  };
}

export function getCumulativeExposurePerMemberMeta(
  members: string[],
  rows: TickerCumulativeExposureRow[],
): CumulativeExposurePerMemberMeta {
  const memberColors = members.map((_, i) => memberColor(i));
  const types = [...new Set(rows.map((r) => r.txn_type_label ?? "Unknown"))];
  return { members, memberColors, typeColors: TYPE_COLORS, types };
}
