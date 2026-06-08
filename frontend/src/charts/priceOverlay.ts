const TYPE_COLORS: Record<string, string> = {
  Buy: "#15803d",
  Sell: "#be123c",
  "Sell (partial)": "#c2410c",
  Exchange: "#1d4ed8",
  Unknown: "#64748b",
};

export type PriceBar = { date: string; close: number };
export type PriceTrade = {
  transaction_date: string;
  y: number | null;
  member: string;
  transaction_type_label?: string;
  txn_type_label?: string;
};

export function buildPriceOverlayOption(
  bars: PriceBar[],
  trades: PriceTrade[],
): Record<string, unknown> | null {
  if (!bars.length && !trades.length) return null;
  const lineSeries = bars.length
    ? {
        name: "Close (Polygon cache)",
        type: "line",
        data: bars.map((b) => [b.date, b.close]),
        showSymbol: false,
        lineStyle: { color: "#20344a", width: 2 },
        itemStyle: { color: "#20344a" },
      }
    : null;

  const types = [...new Set(trades.map((t) => t.transaction_type_label ?? t.txn_type_label ?? "Unknown"))];
  const scatterSeries = types.map((type) => ({
    name: type,
    type: "scatter",
    symbol: "diamond",
    symbolSize: 10,
    data: trades
      .filter((t) => (t.transaction_type_label ?? t.txn_type_label ?? "Unknown") === type)
      .filter((t) => t.y != null)
      .map((t) => [t.transaction_date, t.y, t.member]),
    itemStyle: { color: TYPE_COLORS[type] ?? "#64748b" },
  }));

  return {
    grid: { left: 56, right: 24, top: 24, bottom: 64 },
    xAxis: { type: "time" },
    yAxis: { type: "value", name: "Price" },
    legend: { bottom: 0 },
    series: [...(lineSeries ? [lineSeries] : []), ...scatterSeries],
    tooltip: {
      trigger: "item",
      formatter: (p: { seriesName: string; value: [string, number, string] }) =>
        `${p.value[2] ?? ""}<br/>${p.value[0]}<br/>${p.seriesName}`,
    },
  };
}
