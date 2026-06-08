import type { SparklinePoint } from "@/api/types";

export function buildMiniSparklineOption(
  points: SparklinePoint[],
  color = "#20344a",
): Record<string, unknown> | null {
  if (!points.length) return null;
  const values = points.map((p) => p.value);
  return {
    grid: { left: 0, right: 0, top: 4, bottom: 4 },
    xAxis: { type: "category", show: false, data: points.map((_, i) => i) },
    yAxis: { type: "value", show: false, scale: true },
    series: [
      {
        type: "line",
        data: values,
        smooth: true,
        symbol: "none",
        lineStyle: { width: 2, color },
        areaStyle: { color: `${color}22` },
      },
    ],
    animation: false,
  };
}
