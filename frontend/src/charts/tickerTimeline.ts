import type { TickerTimelineRow } from "@/api/types";

const TYPE_COLORS: Record<string, string> = {
  Buy: "#2f6f4e",
  Sell: "#a64b2a",
  "Sell (partial)": "#c6922b",
  Exchange: "#4a6fa5",
  Unknown: "#64748b",
};

export type TimelineChartOptions = {
  yField?: "member" | "ticker";
  yOrder?: string[];
};

function rowCategory(row: TickerTimelineRow, yField: "member" | "ticker"): string {
  if (yField === "ticker") {
    return String((row as TickerTimelineRow & { ticker?: string }).ticker ?? row.member);
  }
  return row.member;
}

function rowTypeLabel(row: TickerTimelineRow): string {
  return row.txn_type_label ?? (row as TickerTimelineRow & { transaction_type_label?: string }).transaction_type_label ?? "Unknown";
}

// Format the x-axis time tick as a short, scannable date. ECharts' default for
// "time" axes is "yyyy-MM-dd" which is too dense to read at the widths we have.
// The same helper is used by the cumulative-exposure chart so the two timelines
// speak the same date vocabulary.
function formatXDate(value: number): string {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString("en-US", { month: "short", year: "numeric" });
}

// Friendly date for the tooltip ("Mar 12, 2026").
function formatTooltipDate(value: number | string): string {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
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
    symbolSize: 11,
    itemStyle: { color: TYPE_COLORS[type] ?? "#64748b", borderColor: "#ffffff", borderWidth: 1 },
    data: rows
      .filter((r) => rowTypeLabel(r) === type)
      .map((r) => [r.transaction_date, rowCategory(r, yField)]),
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
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: "#1f2937",
        fontSize: 11,
        fontWeight: 500,
        margin: 12,
        width: 120,
        overflow: "truncate",
        ellipsis: "…",
        interval: 0,
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
    series,
    tooltip: {
      trigger: "item",
      formatter: (p: { seriesName: string; value: [string | number, string] }) =>
        `${p.value[1]}<br/>${formatTooltipDate(p.value[0])}<br/>${p.seriesName}`,
    },
  };
}