export type BarChartRow = { label: string; value: number };

export function buildBarChartOption(
  rows: BarChartRow[],
  color = "#20344a",
): Record<string, unknown> | null {
  if (!rows.length) return null;
  const labels = rows.map((r) => r.label);
  const values = rows.map((r) => r.value);
  return {
    grid: { left: 48, right: 24, top: 24, bottom: 64 },
    xAxis: {
      type: "category",
      data: labels,
      axisLabel: { rotate: labels.length > 6 ? 30 : 0, interval: 0 },
    },
    yAxis: { type: "value" },
    series: [
      {
        type: "bar",
        data: values,
        itemStyle: { color },
        label: { show: true, position: "top", formatter: "{c}" },
      },
    ],
    tooltip: { trigger: "axis" },
  };
}
