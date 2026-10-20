import type { NetTradeRow } from "@/api/types";
import { formatCurrency } from "@/utils/format";

import { DIRECTION_COLOR } from "./palette";

export function buildNetTradeOption(rows: NetTradeRow[]): Record<string, unknown> {
  const sorted = [...rows].sort((a, b) => a.net_amount - b.net_amount);
  const tickers = sorted.map((r) => r.ticker);
  const values = sorted.map((r) => r.net_amount);
  return {
    grid: { left: 80, right: 24, top: 12, bottom: 24 },
    // Sign dropped on the axis: left of zero is net selling, shown by the bar colour.
    xAxis: { type: "value", axisLabel: { formatter: (v: number) => (v === 0 ? "$0" : formatCurrency(Math.abs(v))) } },
    yAxis: {
      type: "category",
      data: tickers,
      triggerEvent: true,
      axisLabel: { color: "#1d4ed8", cursor: "pointer" },
    },
    series: [
      {
        type: "bar",
        cursor: "pointer",
        data: values.map((v) => ({
          value: v,
          itemStyle: { color: v >= 0 ? DIRECTION_COLOR.buy : DIRECTION_COLOR.sell },
        })),
      },
    ],
    tooltip: {
      trigger: "axis",
      formatter: (params: { data: { value: number }; name: string }[]) => {
        const p = params[0];
        if (!p) return "";
        return `${p.name}: ${p.data.value >= 0 ? "+" : ""}$${Math.abs(p.data.value).toLocaleString()}`;
      },
    },
  };
}
