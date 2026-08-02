import type { TickerTimelineRow } from "@/api/types";
import { formatCurrency } from "@/utils/format";

const TYPE_COLORS: Record<string, string> = {
  Buy: "#2f6f4e",
  Sell: "#a64b2a",
  "Sell (partial)": "#c6922b",
  Exchange: "#4a6fa5",
  Unknown: "#64748b",
};

/** Pixel diameter range for amount-scaled bubbles. */
const SYMBOL_SIZE_MIN = 8;
const SYMBOL_SIZE_MAX = 28;
const SYMBOL_SIZE_DEFAULT = 11;

export type TimelineChartOptions = {
  yField?: "member" | "ticker";
  yOrder?: string[];
};

type ScatterPoint = [
  string, // transaction_date
  string, // category (member or ticker)
  number, // amount_high (NaN when unknown — drives symbolSize)
];

function rowCategory(row: TickerTimelineRow, yField: "member" | "ticker"): string {
  if (yField === "ticker") {
    return String((row as TickerTimelineRow & { ticker?: string }).ticker ?? row.member);
  }
  return row.member;
}

function rowTypeLabel(row: TickerTimelineRow): string {
  return row.txn_type_label ?? (row as TickerTimelineRow & { transaction_type_label?: string }).transaction_type_label ?? "Unknown";
}

function amountHigh(row: TickerTimelineRow): number | null {
  const n = row.amount_high;
  if (n == null || !Number.isFinite(n) || n < 0) return null;
  return n;
}

/**
 * Map disclosed high amount to bubble diameter via log10 so $1k–$1M+ stay
 * distinguishable without tiny trades vanishing or megatrades dominating.
 */
export function amountToSymbolSize(amount: number | null): number {
  if (amount == null || !Number.isFinite(amount) || amount < 0) {
    return SYMBOL_SIZE_DEFAULT;
  }
  const z = Math.log10(amount + 1);
  // z≈3 ($1k) → near min; z≈6 ($1M) → near max
  const t = Math.min(1, Math.max(0, (z - 3) / 3));
  return SYMBOL_SIZE_MIN + t * (SYMBOL_SIZE_MAX - SYMBOL_SIZE_MIN);
}

// Format the x-axis time tick as a short, scannable date. ECharts' default for
// "time" axes is "yyyy-MM-dd" which is too dense to read at the widths we have.
// The same helper is used by the cumulative-exposure chart so the two timelines
// speak the same date vocabulary.
function parseChartDate(value: number | string): Date | null {
  if (typeof value === "number") {
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? null : d;
  }
  const s = String(value).trim();
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s);
  if (m) {
    const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
    return Number.isNaN(d.getTime()) ? null : d;
  }
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? null : d;
}

function formatXDate(value: number): string {
  const d = parseChartDate(value);
  if (!d) return "";
  return d.toLocaleDateString("en-US", { month: "short", year: "numeric" });
}

// Friendly date for the tooltip ("Mar 12, 2026").
function formatTooltipDate(value: number | string): string {
  const d = parseChartDate(value);
  if (!d) return String(value);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export function buildTickerTimelineOption(
  rows: TickerTimelineRow[],
  options?: TimelineChartOptions,
): Record<string, unknown> | null {
  if (!rows.length) return null;
  const yField = options?.yField ?? "member";
  const memberOrder =
    options?.yOrder?.length
      ? options.yOrder
      : [...new Set(rows.map((r) => rowCategory(r, yField)))];
  const types = [...new Set(rows.map((r) => rowTypeLabel(r)))];
  const series = types.map((type) => ({
    name: type,
    type: "scatter",
    symbolSize: (val: ScatterPoint) => {
      const amt = val[2];
      return amountToSymbolSize(Number.isFinite(amt) ? amt : null);
    },
    itemStyle: { color: TYPE_COLORS[type] ?? "#64748b", borderColor: "#ffffff", borderWidth: 1 },
    data: rows
      .filter((r) => rowTypeLabel(r) === type)
      .map((r): ScatterPoint => {
        const amt = amountHigh(r);
        return [r.transaction_date, rowCategory(r, yField), amt ?? Number.NaN];
      }),
  }));
  return {
    grid: { left: 140, right: 24, top: 24, bottom: 64, containLabel: false },
    // Time axis: friendly month-year labels, hideOverlap so dense ranges stay
    // legible, faint split lines so the eye can chase a date up to its tick.
    xAxis: {
      type: "time",
      name: "Transaction date",
      nameLocation: "middle",
      nameGap: 28,
      nameTextStyle: { color: "#0f172a", fontSize: 12, fontWeight: 600 },
      axisLine: { lineStyle: { color: "#cbd5e1" } },
      axisTick: { lineStyle: { color: "#cbd5e1" } },
      axisLabel: {
        color: "#475569",
        fontSize: 11,
        margin: 12,
        hideOverlap: true,
        formatter: (v: number) => formatXDate(v),
      },
      splitLine: { show: true, lineStyle: { color: "#e2e8f0", type: "dashed" } },
    },
    // Category axis: alternating row backgrounds give each member's swimlane a
    // distinct horizontal band so dots are easy to attribute to a name.
    yAxis: {
      type: "category",
      data: memberOrder,
      inverse: true,
      triggerEvent: true,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: "#1d4ed8",
        fontSize: 11,
        fontWeight: 500,
        margin: 12,
        width: 120,
        overflow: "truncate",
        ellipsis: "…",
        interval: 0,
        cursor: "pointer",
      },
      splitLine: { show: true, lineStyle: { color: "#e2e8f0", type: "dashed" } },
      splitArea: {
        show: true,
        areaStyle: {
          color: ["rgba(241, 245, 249, 0.55)", "rgba(255, 255, 255, 0)"],
        },
      },
    },
    legend: { bottom: 0 },
    series: series.map((s) => ({ ...s, cursor: "pointer" })),
    tooltip: {
      trigger: "item",
      formatter: (p: { seriesName: string; value: ScatterPoint }) => {
        const [date, category, amt] = p.value;
        const amountLine = Number.isFinite(amt)
          ? `<br/>${formatCurrency(amt)} disclosed (high)`
          : "";
        return `${category}<br/>${formatTooltipDate(date)}<br/>${p.seriesName}${amountLine}`;
      },
    },
  };
}
