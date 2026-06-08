import ReactECharts from "echarts-for-react";

import type { CallPutMonthlyRow } from "@/charts/callPutArea";
import { buildCallPutAreaOption } from "@/charts/callPutArea";

type CallPutAreaChartProps = {
  rows: CallPutMonthlyRow[];
  testId?: string;
};

export function CallPutAreaChart({ rows, testId }: CallPutAreaChartProps) {
  const option = buildCallPutAreaOption(rows);
  if (!option) return null;
  return (
    <div data-testid={testId ?? "call-put-area-chart"}>
      <ReactECharts option={option} style={{ height: 280, width: "100%" }} opts={{ renderer: "svg" }} />
    </div>
  );
}
