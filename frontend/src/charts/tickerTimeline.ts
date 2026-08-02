import type { TickerTimelineRow } from "@/api/types";
import { formatCurrency } from "@/utils/format";

/** Visual encoding for each disclosure type — shape + color + plain-language action. */
type TypeVisual = {
  color: string;
  /** ECharts built-in symbol name. */
  symbol: "triangle" | "diamond" | "circle" | "roundRect";
  symbolRotate?: number;
  /** Legend / series label with action cue. */
  legend: string;
  /** Short verb for tooltips. */
  action: string;
};

const TYPE_VISUAL: Record<string, TypeVisual> = {
  Buy: {
    color: "#2f6f4e",
    symbol: "triangle",
    legend: "Buy · increased",
    action: "Bought / increased",
  },
  "Sell (partial)": {
    color: "#c6922b",
    symbol: "diamond",
    legend: "Partial sell · reduced",
    action: "Reduced (partial sell)",
  },
  Sell: {
    color: "#a64b2a",
    symbol: "triangle",
    symbolRotate: 180,
    legend: "Sell · exited",
    action: "Sold / exited",
  },
  Exchange: {
    color: "#4a6fa5",
    symbol: "roundRect",
    legend: "Exchange",
    action: "Exchanged",
  },
  Unknown: {
    color: "#64748b",
    symbol: "circle",
    legend: "Unknown",
    action: "Unknown type",
  },
};

const TYPE_ORDER = ["Buy", "Sell (partial)", "Sell", "Exchange", "Unknown"] as const;

const FALLBACK_VISUAL: TypeVisual = {
  color: "#64748b",
  symbol: "circle",
  legend: "Other",
  action: "Other",
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

function visualFor(type: string): TypeVisual {
  return TYPE_VISUAL[type] ?? { ...FALLBACK_VISUAL, legend: type, action: type };
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

function orderedTypes(present: Iterable<string>): string[] {
  const set = new Set(present);
  const ordered: string[] = TYPE_ORDER.filter((t) => set.has(t));
  for (const t of set) {
    if (!ordered.includes(t)) ordered.push(t);
  }
  return ordered;
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
  const types = orderedTypes(rows.map((r) => rowTypeLabel(r)));
  const series = types.map((type) => {
    const visual = visualFor(type);
    return {
      // Canonical type id — tooltip reads this for action wording.
      id: type,
      name: visual.legend,
      type: "scatter" as const,
      symbol: visual.symbol,
      symbolRotate: visual.symbolRotate ?? 0,
      cursor: "pointer",
      symbolSize: (val: ScatterPoint) => {
        const amt = val[2];
        return amountToSymbolSize(Number.isFinite(amt) ? amt : null);
      },
      itemStyle: {
        color: visual.color,
        borderColor: "#ffffff",
        borderWidth: 1,
      },
      data: rows
        .filter((r) => rowTypeLabel(r) === type)
        .map((r): ScatterPoint => {
          const amt = amountHigh(r);
          return [r.transaction_date, rowCategory(r, yField), amt ?? Number.NaN];
        }),
    };
  });
  return {
    grid: { left: 140, right: 24, top: 24, bottom: 72, containLabel: false },
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
    legend: {
      bottom: 0,
      itemWidth: 14,
      itemHeight: 10,
      textStyle: { fontSize: 11, color: "#334155" },
    },
    series,
    tooltip: {
      trigger: "item",
      formatter: (p: { seriesId?: string; seriesName: string; value: ScatterPoint }) => {
        const [date, category, amt] = p.value;
        const typeKey = p.seriesId || "Unknown";
        const visual = visualFor(typeKey);
        const amountLine = Number.isFinite(amt)
          ? `<br/><span style="color:#64748b">Disclosed high:</span> ${formatCurrency(amt)}`
          : "<br/><span style=\"color:#64748b\">Disclosed high: unknown</span>";
        return (
          `<strong>${category}</strong>` +
          `<br/>${formatTooltipDate(date)}` +
          `<br/><span style="color:${visual.color};font-weight:600">${visual.action}</span>` +
          amountLine
        );
      },
    },
  };
}
