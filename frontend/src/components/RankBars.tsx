import ReactECharts from "echarts-for-react";

import { buildRankBarsOption, type RankBarRow } from "@/charts/rankBars";

type RankBarsProps = {
  rows: RankBarRow[];
  color?: string;
  testId?: string;
};

export function RankBars({ rows, color, testId }: RankBarsProps) {
  if (!rows.length) return null;
  return (
    <div data-testid={testId}>
      <ReactECharts
        option={buildRankBarsOption(rows, color)}
        style={{ height: Math.max(220, rows.length * 28), width: "100%" }}
        opts={{ renderer: "svg" }}
        data-testid="rank-bars-chart"
      />
    </div>
  );
}
