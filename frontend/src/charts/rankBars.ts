export type RankBarRow = { label: string; value: number; detail?: string };

export function buildRankBarsOption(rows: RankBarRow[], color = "#20344a"): Record<string, unknown> {
  const labels = rows.map((r) => r.label).reverse();
  const values = rows.map((r) => r.value).reverse();
  return {
    grid: { left: 120, right: 24, top: 12, bottom: 24 },
    xAxis: { type: "value" },
    yAxis: { type: "category", data: labels, axisLabel: { width: 110, overflow: "truncate" } },
    series: [
      {
        type: "bar",
        data: values,
        itemStyle: { color },
        label: { show: true, position: "right", formatter: "{c}" },
      },
    ],
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
  };
}
