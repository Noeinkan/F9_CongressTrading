import { buildBarChartOption, type BarChartRow } from "@/charts/barChart";

import { EChartsChart } from "./EChartsChart";

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
      <EChartsChart
        option={option}
        height={Math.max(220, rows.length * 40)}
        testId="bar-chart"
      />
    </div>
  );
}
