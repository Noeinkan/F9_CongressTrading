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
    symbolSize: 10,
    itemStyle: { color: TYPE_COLORS[type] ?? "#64748b" },
    data: rows
      .filter((r) => rowTypeLabel(r) === type)
      .map((r) => [r.transaction_date, rowCategory(r, yField)]),
  }));
  return {
    grid: { left: 120, right: 24, top: 24, bottom: 48 },
    xAxis: { type: "time" },
    yAxis: { type: "category", data: memberOrder, inverse: true },
    legend: { bottom: 0 },
    series,
    tooltip: {
      trigger: "item",
      formatter: (p: { seriesName: string; value: [string, string] }) =>
        `${p.value[1]}<br/>${p.value[0]}<br/>${p.seriesName}`,
    },
  };
}
