import type { TickerCumulativeRow } from "@/api/types";

export function buildCumulativeExposureOption(rows: TickerCumulativeRow[]): Record<string, unknown> | null {
  if (!rows.length) return null;
  const members = [...new Set(rows.map((r) => r.member))].slice(0, 16);
  const series = members.map((member) => ({
    name: member,
    type: "line",
    step: "end",
    showSymbol: false,
    data: rows
      .filter((r) => r.member === member)
      .map((r) => [r.date, r.cumulative_net]),
  }));
  return {
    grid: { left: 64, right: 24, top: 24, bottom: 64 },
    xAxis: { type: "time" },
    yAxis: { type: "value", name: "Cumulative net ($)" },
    legend: { type: "scroll", bottom: 0 },
    series,
    tooltip: { trigger: "axis" },
  };
}
