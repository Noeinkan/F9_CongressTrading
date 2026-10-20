import { formatCompact } from "@/utils/format";

export type BarChartRow = { label: string; value: number };

/**
 * Categories here are names (review reasons, statuses), so the bars run
 * horizontally: the full label reads left to right instead of tilting under
 * the axis. Rows keep their given order, first row on top.
 */
export function buildBarChartOption(
  rows: BarChartRow[],
  color = "#20344a",
): Record<string, unknown> | null {
  if (!rows.length) return null;
  const labels = rows.map((r) => r.label).reverse();
  const values = rows.map((r) => r.value).reverse();
  return {
    grid: { left: 16, right: 48, top: 12, bottom: 24, containLabel: true },
    xAxis: { type: "value", axisLabel: { formatter: (v: number) => formatCompact(v) } },
    yAxis: {
      type: "category",
      data: labels,
      // Long reasons are cut on the axis; the tooltip carries the full text.
      axisLabel: { width: 180, overflow: "truncate" },
    },
    series: [
      {
        type: "bar",
        data: values,
        itemStyle: { color },
        label: {
          show: true,
          position: "right",
          formatter: (p: { value: number }) => formatCompact(p.value),
        },
      },
    ],
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
  };
}
