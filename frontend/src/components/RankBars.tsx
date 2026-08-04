import { useNavigate } from "react-router-dom";

import { buildRankBarsOption, type RankBarRow } from "@/charts/rankBars";
import { hrefFromChartClick, type EntityLinkKind } from "@/utils/entityLinks";

import { EChartsChart } from "./EChartsChart";

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
      }
    : undefined;

  return (
    <div data-testid={testId}>
      <EChartsChart
        option={buildRankBarsOption(rows, color, Boolean(linkKind))}
        height={Math.max(220, rows.length * 28)}
        onEvents={onEvents}
        testId="rank-bars-chart"
      />
    </div>
  );
}
