import type { CallPutRatioRow } from "@/charts/callPutRatio";
import { buildCallPutRatioOption } from "@/charts/callPutRatio";

import { EChartsChart } from "./EChartsChart";

type CallPutRatioChartProps = {
  rows: CallPutRatioRow[];
  testId?: string;
};

export function CallPutRatioChart({ rows, testId }: CallPutRatioChartProps) {
  return (
    <EChartsChart
      option={buildCallPutRatioOption(rows)}
      height={280}
      testId={testId ?? "call-put-ratio-chart"}
    />
  );
}
