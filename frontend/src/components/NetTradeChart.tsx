import ReactECharts from "echarts-for-react";
import { useNavigate } from "react-router-dom";

import type { NetTradeRow } from "@/api/types";
import { buildNetTradeOption } from "@/charts/netTrade";
import { hrefFromChartClick } from "@/utils/entityLinks";

type NetTradeChartProps = {
  rows: NetTradeRow[];
};

export function NetTradeChart({ rows }: NetTradeChartProps) {
  const navigate = useNavigate();
  if (!rows.length) return null;
  return (
    <ReactECharts
      option={buildNetTradeOption(rows)}
      style={{ height: Math.max(220, rows.length * 28), width: "100%" }}
      opts={{ renderer: "svg" }}
      onEvents={{
        click: (params: {
          componentType?: string;
          name?: string;
          value?: unknown;
          seriesName?: string;
        }) => {
          const href = hrefFromChartClick(params, "ticker");
          if (href) navigate(href);
        },
      }}
      data-testid="net-trade-chart"
    />
  );
}
