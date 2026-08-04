import {
  buildSectorHeatmapOption,
  type SectorMonthlyRow,
} from "@/charts/sectorHeatmap";

import { EChartsChart } from "./EChartsChart";

type SectorHeatmapChartProps = {
  rows: SectorMonthlyRow[];
  testId?: string;
};

export function SectorHeatmapChart({ rows, testId }: SectorHeatmapChartProps) {
  const option = buildSectorHeatmapOption(rows);
  if (!option) return null;
  const { chartHeight, ...echartsOption } = option;
  const height = typeof chartHeight === "number" ? chartHeight : 280;
  return (
    <EChartsChart
      option={echartsOption}
      height={height}
      testId={testId ?? "sector-heatmap-chart"}
    />
  );
}
