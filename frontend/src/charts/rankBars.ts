import { formatCompact } from "@/utils/format";

export type RankBarRow = { label: string; value: number; detail?: string };

export function buildRankBarsOption(
  rows: RankBarRow[],
  color = "#20344a",
  clickable = false,
): Record<string, unknown> {
  const labels = rows.map((r) => r.label).reverse();
  const values = rows.map((r) => r.value).reverse();
  return {
    grid: { left: 120, right: 40, top: 12, bottom: 24 },
    xAxis: { type: "value", axisLabel: { formatter: (v: number) => formatCompact(v) } },
    yAxis: {
      type: "category",
      data: labels,
      triggerEvent: clickable,
      axisLabel: {
        width: 110,
        overflow: "truncate",
        ...(clickable ? { color: "#1d4ed8", cursor: "pointer" } : {}),
      },
    },
    series: [
      {
        type: "bar",
        data: values,
        itemStyle: { color },
        // "1.2K", not "1234", so the label never runs past the card.
        label: {
          show: true,
          position: "right",
          formatter: (p: { value: number }) => formatCompact(p.value),
        },
        cursor: clickable ? "pointer" : "default",
      },
    ],
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
  };
}
