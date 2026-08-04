import type { CallPutMonthlyRow } from "@/charts/callPutArea";
import { buildCallPutAreaOption } from "@/charts/callPutArea";

import { EChartsChart } from "./EChartsChart";

type CallPutAreaChartProps = {
  rows: CallPutMonthlyRow[];
  testId?: string;
};

export function CallPutAreaChart({ rows, testId }: CallPutAreaChartProps) {
  return (
    <EChartsChart
      option={buildCallPutAreaOption(rows)}
      height={280}
      testId={testId ?? "call-put-area-chart"}
    />
  );
}
