import ReactECharts from "echarts-for-react";

import type { CallPutRatioRow } from "@/charts/callPutRatio";
import { buildCallPutRatioOption } from "@/charts/callPutRatio";

type CallPutRatioChartProps = {
  rows: CallPutRatioRow[];
  testId?: string;
};

export function CallPutRatioChart({ rows, testId }: CallPutRatioChartProps) {
  const option = buildCallPutRatioOption(rows);
  if (!option) return null;
  return (
    <div data-testid={testId ?? "call-put-ratio-chart"}>
      <ReactECharts option={option} style={{ height: 280, width: "100%" }} opts={{ renderer: "svg" }} />
    </div>
  );
}
