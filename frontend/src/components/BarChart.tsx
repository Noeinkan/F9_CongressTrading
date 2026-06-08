import ReactECharts from "echarts-for-react";

import { buildBarChartOption, type BarChartRow } from "@/charts/barChart";

type BarChartProps = {
  rows: BarChartRow[];
  color?: string;
  testId?: string;
};

export function BarChart({ rows, color, testId }: BarChartProps) {
  const option = buildBarChartOption(rows, color);
  if (!option) return null;
  return (
    <div data-testid={testId}>
      <ReactECharts
        option={option}
        style={{ height: Math.max(220, rows.length * 40), width: "100%" }}
        opts={{ renderer: "svg" }}
        data-testid="bar-chart"
      />
    </div>
  );
}
