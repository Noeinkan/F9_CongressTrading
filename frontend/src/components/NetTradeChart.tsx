import ReactECharts from "echarts-for-react";

import type { NetTradeRow } from "@/api/types";
import { buildNetTradeOption } from "@/charts/netTrade";

type NetTradeChartProps = {
  rows: NetTradeRow[];
};

export function NetTradeChart({ rows }: NetTradeChartProps) {
  if (!rows.length) return null;
  return (
    <ReactECharts
      option={buildNetTradeOption(rows)}
      style={{ height: Math.max(220, rows.length * 28), width: "100%" }}
      opts={{ renderer: "svg" }}
      data-testid="net-trade-chart"
    />
  );
}
