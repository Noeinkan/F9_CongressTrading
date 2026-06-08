import ReactECharts from "echarts-for-react";

import type { SparklinePoint } from "@/api/types";
import { buildMiniSparklineOption } from "@/charts/miniSparkline";

type MiniSparklineProps = {
  points: SparklinePoint[];
  height?: number;
  color?: string;
};

export function MiniSparkline({ points, height = 40, color }: MiniSparklineProps) {
  const option = buildMiniSparklineOption(points, color);
  if (!option) return null;
  return (
    <div data-testid="mini-sparkline">
      <ReactECharts
        option={option}
        style={{ height, width: "100%" }}
        opts={{ renderer: "svg" }}
      />
    </div>
  );
}
