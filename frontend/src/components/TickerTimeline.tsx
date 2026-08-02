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
  // Remount when the category axis mode/order changes so ECharts option-merge
  // cannot leave a prior page's y-axis categories (e.g. members vs tickers).
  const chartKey = `${yField ?? "member"}:${(yOrder ?? []).join("|")}:${rows.length}`;
  return (
    <ReactECharts
      key={chartKey}
      option={option}
      notMerge
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
