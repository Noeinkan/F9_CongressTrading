import ReactECharts from "echarts-for-react";

import { buildMonthlyActivityOption, type MonthlyActivityRow } from "@/charts/monthlyActivity";

type MonthlyActivityChartProps = {
  rows: MonthlyActivityRow[];
};

export function MonthlyActivityChart({ rows }: MonthlyActivityChartProps) {
  if (!rows.length) return null;
  return (
    <ReactECharts
      option={buildMonthlyActivityOption(rows)}
      style={{ height: 280, width: "100%" }}
      opts={{ renderer: "svg" }}
      data-testid="monthly-activity-chart"
    />
  );
}
