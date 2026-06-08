import { Alert } from "@mantine/core";
import ReactECharts from "echarts-for-react";

import type { TickerCumulativeExposureRow } from "@/api/types";
import { buildCumulativeExposurePerMemberOption } from "@/charts/cumulativeExposurePerMember";
import { COPY } from "@/copy";

type CumulativeExposurePerMemberProps = {
  ticker: string;
  members: string[];
  rows: TickerCumulativeExposureRow[];
  truncated?: boolean;
};

export function CumulativeExposurePerMember({
  members,
  rows,
  truncated,
}: CumulativeExposurePerMemberProps) {
  const option = buildCumulativeExposurePerMemberOption(rows, members);
  return (
    <div data-testid="cumulative-exposure-per-member">
      <Alert color="orange" variant="light" mb="sm" data-testid="cumulative-guide">
        <strong>{COPY.tickers.cumulativeGuideTitle}</strong> — {COPY.tickers.cumulativeGuideLines}
        <br />
        <span style={{ fontSize: "0.85em" }}>{COPY.tickers.cumulativeGuideNote}</span>
      </Alert>
      {truncated ? (
        <Alert color="gray" variant="light" mb="sm">
          Showing top {members.length} members by trade count.
        </Alert>
      ) : null}
      {option ? (
        <ReactECharts
          option={option}
          style={{ height: Math.max(360, members.length * 78), width: "100%" }}
          opts={{ renderer: "svg" }}
          data-testid="cumulative-exposure-chart"
        />
      ) : null}
    </div>
  );
}
