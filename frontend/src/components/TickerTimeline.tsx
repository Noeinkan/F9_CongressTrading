import ReactECharts from "echarts-for-react";
import { useNavigate } from "react-router-dom";

import type { TickerTimelineRow } from "@/api/types";
import { buildTickerTimelineOption, type TimelineChartOptions } from "@/charts/tickerTimeline";
import { hrefFromChartClick } from "@/utils/entityLinks";

type TickerTimelineProps = {
  rows: TickerTimelineRow[];
  yField?: TimelineChartOptions["yField"];
  yOrder?: string[];
  testId?: string;
};

export function TickerTimeline({ rows, yField, yOrder, testId }: TickerTimelineProps) {
  const navigate = useNavigate();
  const option = buildTickerTimelineOption(rows, { yField, yOrder });
  if (!option) return null;
  const height = Math.max(240, (yOrder?.length ?? rows.length) * 28);
  const linkKind = yField === "ticker" ? "ticker" : "member";
  return (
    <ReactECharts
      option={option}
      style={{ height, width: "100%" }}
      opts={{ renderer: "svg" }}
      onEvents={{
        click: (params: {
          componentType?: string;
          name?: string;
          value?: unknown;
          seriesName?: string;
        }) => {
          const href = hrefFromChartClick(params, linkKind);
          if (href) navigate(href);
        },
      }}
      data-testid={testId ?? "ticker-timeline-chart"}
    />
  );
}
