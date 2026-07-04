import { Alert, Box, Group, Stack, Text } from "@mantine/core";
import { useMemo } from "react";
import ReactECharts from "echarts-for-react";

import type { TickerCumulativeExposureRow } from "@/api/types";
import {
  buildCumulativeExposurePerMemberOption,
  getCumulativeExposurePerMemberMeta,
} from "@/charts/cumulativeExposurePerMember";
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
  // Same ordering as the chart (largest absolute net first) so the legend
  // matches the swimlanes top-to-bottom.
  const orderedMembers = useMemo(() => {
    // Last-seen net per member (rows arrive chronologically, so the final
    // write is the member's current net).
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

      {meta.types.length ? (
        <Box
          mb="sm"
          p="xs"
          style={{
            background: "#f8fafc",
            border: "1px solid #e2e8f0",
            borderRadius: 6,
          }}
          data-testid="cumulative-legend"
        >
          <Group gap="md" wrap="wrap" align="center">
            <Text size="xs" fw={600} c="dark.5">
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
                  <Text size="xs" c="dark.4">
                    {type}
                  </Text>
                </Group>
              ))}
            </Group>
            <Text size="xs" fw={600} c="dark.5" ml="md">
              Members
            </Text>
            <Group gap="sm" wrap="wrap">
              {meta.members.map((m, i) => (
                <Group gap={6} key={m} wrap="nowrap">
                  <span
                    aria-hidden
                    style={{
                      display: "inline-block",
                      width: 10,
                      height: 10,
                      borderRadius: 2,
                      background: meta.memberColors[i] ?? "#94a3b8",
                    }}
                  />
                  <Text size="xs" c="dark.4">
                    {m}
                  </Text>
                </Group>
              ))}
            </Group>
          </Group>
        </Box>
      ) : null}

      <Stack gap={2} mb="xs">
        <Text size="xs" c="dimmed">
          Each tinted band (with a colored left stripe and matching name pill)
          is one member's swimlane, ordered by absolute net exposure (largest
          at the top). Step up = buy, step down = sell, flat = no new trades.
          The x-axis is the transaction date. The dashed line in every lane
          marks the $0 break-even; y-ticks are in disclosed dollars.
        </Text>
      </Stack>

      {option ? (
        <ReactECharts
          option={option}
          style={{ height: Math.max(360, members.length * 100 + 56), width: "100%" }}
          opts={{ renderer: "svg" }}
          data-testid="cumulative-exposure-chart"
        />
      ) : null}
    </div>
  );
}
