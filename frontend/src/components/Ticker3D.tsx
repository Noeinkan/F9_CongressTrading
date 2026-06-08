import { Alert } from "@mantine/core";
import ReactECharts from "echarts-for-react";
import { useMemo } from "react";

import type { Ticker3DRow } from "@/api/types";
import { buildTicker3DOption } from "@/charts/ticker3d";

function webglAvailable(): boolean {
  if (typeof document === "undefined") return true;
  if (typeof HTMLCanvasElement === "undefined") return false;
  try {
    const canvas = document.createElement("canvas");
    if (typeof canvas.getContext !== "function") return false;
    const ctx = canvas.getContext("webgl") ?? canvas.getContext("experimental-webgl");
    return !!ctx;
  } catch {
    return false;
  }
}

type Ticker3DProps = {
  rows: Ticker3DRow[];
};

export function Ticker3D({ rows }: Ticker3DProps) {
  const canRender = useMemo(() => webglAvailable(), []);
  const option = buildTicker3DOption(rows);

  if (!canRender) {
    return (
      <Alert color="orange" title="3D view unavailable" data-testid="ticker-3d-fallback">
        Your browser does not support WebGL. Use the timeline or cumulative charts instead.
      </Alert>
    );
  }
  if (!option) return null;
  return (
    <ReactECharts
      option={option}
      style={{ height: 480, width: "100%" }}
      opts={{ renderer: "canvas" }}
      data-testid="ticker-3d-chart"
    />
  );
}
