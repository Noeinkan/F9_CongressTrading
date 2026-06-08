import { Alert } from "@mantine/core";
import ReactECharts from "echarts-for-react";

import type { TickerCumulativeRow } from "@/api/types";
import { buildCumulativeExposureOption } from "@/charts/cumulativeExposure";

type CumulativeExposureProps = {
  rows: TickerCumulativeRow[];
  ticker: string;
};

export function CumulativeExposure({ rows, ticker }: CumulativeExposureProps) {
  const option = buildCumulativeExposureOption(rows);
  return (
    <div>
      <Alert color="orange" variant="light" mb="sm" data-testid="cumulative-guide">
        Running net signed notional per member for <strong>{ticker}</strong>. Step lines rise on buys
        and fall on sells; the $0 line marks flat exposure.
      </Alert>
      {option ? (
        <ReactECharts
          option={option}
          style={{ height: 360, width: "100%" }}
          opts={{ renderer: "svg" }}
          data-testid="cumulative-exposure-chart"
        />
      ) : null}
    </div>
  );
}
