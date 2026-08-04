import { Alert, Box, Group, Text } from "@mantine/core";
import { useMemo } from "react";
import ReactECharts from "echarts-for-react";
import { useNavigate } from "react-router-dom";

import type { TickerCumulativeExposureRow } from "@/api/types";
import {
  buildCumulativeExposurePerMemberOption,
  CUMULATIVE_EXPOSURE_CHART_HEIGHT,
  getCumulativeExposurePerMemberMeta,
} from "@/charts/cumulativeExposurePerMember";
import { COPY } from "@/copy";
import { hrefFromChartClick } from "@/utils/entityLinks";

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
  const navigate = useNavigate();
  // Same ordering as the chart (largest absolute net first) so the
  // trade-type key sits above a legend that matches series priority.
  const orderedMembers = useMemo(() => {
    const lastNetByMember = new Map<string, number>();
    rows.forEach((r) => {
      lastNetByMember.set(r.member, r.cumulative_net);
    });
    return [...members].sort((a, b) => {
      const ra = Math.abs(lastNetByMember.get(a) ?? 0);
      const rb = Math.abs(lastNetByMember.get(b) ?? 0);
      if (rb !== ra) return rb - ra;
      return a.localeCompare(b);
    });
  }, [members, rows]);

  const option = buildCumulativeExposurePerMemberOption(rows, members);
  const meta = getCumulativeExposurePerMemberMeta(orderedMembers, rows);

  return (
    <div data-testid="cumulative-exposure-per-member">
      <Alert color="orange" variant="light" mb="sm" data-testid="cumulative-guide" py={8}>
        <Text size="xs">
          <strong>{COPY.tickers.cumulativeGuideTitle}</strong> — {COPY.tickers.cumulativeGuideLines}
        </Text>
        <Text size="xs" c="dimmed" mt={4}>
          {COPY.tickers.cumulativeGuideNote}
        </Text>
      </Alert>
      {truncated ? (
        <Alert color="gray" variant="light" mb="sm" py={6}>
          Showing top {members.length} members by trade count.
        </Alert>
      ) : null}

      {meta.types.length ? (
        <Box
          mb="xs"
          px="xs"
          py={6}
          style={{
            background: "#f8fafc",
            border: "1px solid #e2e8f0",
            borderRadius: 6,
          }}
          data-testid="cumulative-legend"
        >
          <Group gap="md" wrap="wrap" align="center">
            <Text size="xs" fw={700} c="dark.6">
              Trades
            </Text>
            <Group gap="sm" wrap="wrap">
              {meta.types.map((type) => (
                <Group gap={6} key={type} wrap="nowrap">
                  <span
                    aria-hidden
                    style={{
                      display: "inline-block",
                      width: 9,
                      height: 9,
                      borderRadius: "50%",
                      background: meta.typeColors[type] ?? "#64748b",
                      border: "1.5px solid #fff",
                      boxShadow: "0 0 0 1px rgba(15,23,42,0.08)",
                    }}
                  />
                  <Text size="xs" fw={500} c="dark.5">
                    {type}
                  </Text>
                </Group>
              ))}
            </Group>
            <Text size="xs" c="dimmed" ml="sm">
              Click a member in the chart legend to hide or show their line.
            </Text>
          </Group>
        </Box>
      ) : null}

      {option ? (
        <ReactECharts
          option={option}
          notMerge
          lazyUpdate
          style={{ height: CUMULATIVE_EXPOSURE_CHART_HEIGHT, width: "100%" }}
          opts={{ renderer: "svg" }}
          onEvents={{
            click: (params: {
              componentType?: string;
              name?: string;
              value?: unknown;
              seriesName?: string;
            }) => {
              const href = hrefFromChartClick(params, "member");
              if (href) navigate(href);
            },
          }}
          data-testid="cumulative-exposure-chart"
        />
      ) : null}
    </div>
  );
}
