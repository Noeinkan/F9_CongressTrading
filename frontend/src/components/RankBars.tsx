import ReactECharts from "echarts-for-react";
import { useNavigate } from "react-router-dom";

import { buildRankBarsOption, type RankBarRow } from "@/charts/rankBars";
import { hrefFromChartClick, type EntityLinkKind } from "@/utils/entityLinks";

type RankBarsProps = {
  rows: RankBarRow[];
  color?: string;
  testId?: string;
  /** When set, clicking a bar or y-axis label navigates to that entity. */
  linkKind?: EntityLinkKind;
};

export function RankBars({ rows, color, testId, linkKind }: RankBarsProps) {
  const navigate = useNavigate();
  if (!rows.length) return null;

  const onEvents = linkKind
    ? {
        click: (params: {
          componentType?: string;
          name?: string;
          value?: unknown;
          seriesName?: string;
        }) => {
          const href = hrefFromChartClick(params, linkKind);
          if (href) navigate(href);
        },
      }
    : undefined;

  return (
    <div data-testid={testId}>
      <ReactECharts
        option={buildRankBarsOption(rows, color, Boolean(linkKind))}
        style={{ height: Math.max(220, rows.length * 28), width: "100%" }}
        opts={{ renderer: "svg" }}
        onEvents={onEvents}
        data-testid="rank-bars-chart"
      />
    </div>
  );
}
