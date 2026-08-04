import { useNavigate } from "react-router-dom";

import type { NetTradeRow } from "@/api/types";
import { buildNetTradeOption } from "@/charts/netTrade";
import { hrefFromChartClick } from "@/utils/entityLinks";

import { EChartsChart } from "./EChartsChart";

type NetTradeChartProps = {
  rows: NetTradeRow[];
};

export function NetTradeChart({ rows }: NetTradeChartProps) {
  const navigate = useNavigate();
  if (!rows.length) return null;
  return (
    <EChartsChart
      option={buildNetTradeOption(rows)}
      height={Math.max(220, rows.length * 28)}
      testId="net-trade-chart"
      onEvents={{
        click: (params: unknown) => {
          const href = hrefFromChartClick(
            params as {
              componentType?: string;
              name?: string;
              value?: unknown;
              seriesName?: string;
            },
            "ticker",
          );
          if (href) navigate(href);
        },
      }}
    />
  );
}
