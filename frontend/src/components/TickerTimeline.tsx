import { useNavigate } from "react-router-dom";

import type { TickerTimelineRow } from "@/api/types";
import { buildTickerTimelineOption, type TimelineChartOptions } from "@/charts/tickerTimeline";
import { hrefFromChartClick } from "@/utils/entityLinks";

import { EChartsChart } from "./EChartsChart";

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
    <EChartsChart
      key={chartKey}
      option={option}
      height={height}
      notMerge
      testId={testId ?? "ticker-timeline-chart"}
      onEvents={{
        click: (params: unknown) => {
          const href = hrefFromChartClick(
            params as {
              componentType?: string;
              name?: string;
              value?: unknown;
              seriesName?: string;
            },
            linkKind,
          );
          if (href) navigate(href);
        },
      }}
    />
  );
}
