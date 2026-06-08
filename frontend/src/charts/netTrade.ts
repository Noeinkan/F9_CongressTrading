import type { NetTradeRow } from "@/api/types";

export function buildNetTradeOption(rows: NetTradeRow[]): Record<string, unknown> {
  const sorted = [...rows].sort((a, b) => a.net_amount - b.net_amount);
  const tickers = sorted.map((r) => r.ticker);
  const values = sorted.map((r) => r.net_amount);
  return {
    grid: { left: 80, right: 24, top: 12, bottom: 24 },
    xAxis: { type: "value", axisLabel: { formatter: (v: number) => `$${Math.abs(v / 1000).toFixed(0)}K` } },
    yAxis: { type: "category", data: tickers },
    series: [
      {
        type: "bar",
        data: values.map((v) => ({
          value: v,
          itemStyle: { color: v >= 0 ? "#2f6f4e" : "#a64b2a" },
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
