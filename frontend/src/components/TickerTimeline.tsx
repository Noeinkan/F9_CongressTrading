import ReactECharts from "echarts-for-react";

import type { TickerTimelineRow } from "@/api/types";
import { buildTickerTimelineOption, type TimelineChartOptions } from "@/charts/tickerTimeline";

type TickerTimelineProps = {
  rows: TickerTimelineRow[];
  yField?: TimelineChartOptions["yField"];
  yOrder?: string[];
  testId?: string;
};

export function TickerTimeline({ rows, yField, yOrder, testId }: TickerTimelineProps) {
  const option = buildTickerTimelineOption(rows, { yField, yOrder });
  if (!option) return null;
  const height = Math.max(240, (yOrder?.length ?? rows.length) * 28);
  return (
    <ReactECharts
      option={option}
      style={{ height, width: "100%" }}
      opts={{ renderer: "svg" }}
      data-testid={testId ?? "ticker-timeline-chart"}
    />
  );
}
