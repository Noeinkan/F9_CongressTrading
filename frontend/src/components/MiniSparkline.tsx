import type { SparklinePoint } from "@/api/types";
import { buildMiniSparklineOption } from "@/charts/miniSparkline";

import { EChartsChart } from "./EChartsChart";

type MiniSparklineProps = {
  points: SparklinePoint[];
  height?: number;
  color?: string;
};

export function MiniSparkline({ points, height = 40, color }: MiniSparklineProps) {
  return (
    <EChartsChart
      option={buildMiniSparklineOption(points, color)}
      height={height}
      testId="mini-sparkline"
    />
  );
}
