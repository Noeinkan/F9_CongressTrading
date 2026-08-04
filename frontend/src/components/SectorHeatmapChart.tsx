import ReactECharts from "echarts-for-react";

import {
  buildSectorHeatmapOption,
  type SectorMonthlyRow,
} from "@/charts/sectorHeatmap";

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
    <div data-testid={testId ?? "sector-heatmap-chart"}>
      <ReactECharts
        option={echartsOption}
        style={{ height, width: "100%" }}
        opts={{ renderer: "svg" }}
      />
    </div>
  );
}
