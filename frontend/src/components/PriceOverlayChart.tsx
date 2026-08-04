import type { PriceBar, PriceTrade } from "@/charts/priceOverlay";
import { buildPriceOverlayOption } from "@/charts/priceOverlay";

import { EChartsChart } from "./EChartsChart";

type PriceOverlayChartProps = {
  bars: PriceBar[];
  trades: PriceTrade[];
  testId?: string;
};

export function PriceOverlayChart({ bars, trades, testId }: PriceOverlayChartProps) {
  return (
    <EChartsChart
      option={buildPriceOverlayOption(bars, trades)}
      height={360}
      testId={testId ?? "price-overlay-chart"}
    />
  );
}
