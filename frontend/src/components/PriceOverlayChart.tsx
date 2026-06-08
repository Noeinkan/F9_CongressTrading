import ReactECharts from "echarts-for-react";

import type { PriceBar, PriceTrade } from "@/charts/priceOverlay";
import { buildPriceOverlayOption } from "@/charts/priceOverlay";

type PriceOverlayChartProps = {
  bars: PriceBar[];
  trades: PriceTrade[];
  testId?: string;
};

export function PriceOverlayChart({ bars, trades, testId }: PriceOverlayChartProps) {
  const option = buildPriceOverlayOption(bars, trades);
  if (!option) return null;
  return (
    <div data-testid={testId ?? "price-overlay-chart"}>
      <ReactECharts option={option} style={{ height: 360, width: "100%" }} opts={{ renderer: "svg" }} />
    </div>
  );
}
