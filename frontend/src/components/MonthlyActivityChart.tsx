import { buildMonthlyActivityOption, type MonthlyActivityRow } from "@/charts/monthlyActivity";

import { EChartsChart } from "./EChartsChart";

type MonthlyActivityChartProps = {
  rows: MonthlyActivityRow[];
};

export function MonthlyActivityChart({ rows }: MonthlyActivityChartProps) {
  if (!rows.length) return null;
  return (
    <EChartsChart
      option={buildMonthlyActivityOption(rows)}
      height={320}
      testId="monthly-activity-chart"
    />
  );
}
