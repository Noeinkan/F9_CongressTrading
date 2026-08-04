import { Badge, Paper, Stack, Text, Title } from "@mantine/core";

import type { KpiDelta, SparklinePoint } from "@/api/types";

import { MiniSparkline } from "./MiniSparkline";

export type KpiTileSpec = {
  key: string;
  label: string;
  value: string | number;
  detail?: string;
  sparkline?: SparklinePoint[];
  delta?: KpiDelta | null;
};

type KpiTileProps = {
  kpi: KpiTileSpec;
};

export function KpiTile({ kpi }: KpiTileProps) {
  const delta = kpi.delta;
  const deltaColor = delta
    ? delta.value > 0
      ? "teal"
      : delta.value < 0
        ? "red"
        : "gray"
    : "gray";

  return (
    <Paper p="md" radius="md" withBorder data-testid={`kpi-tile-${kpi.key}`}>
      <Stack gap={6}>
        <Text size="xs" c="dimmed" tt="uppercase" fw={700}>
          {kpi.label}
        </Text>
        <Title order={3}>{String(kpi.value)}</Title>
        {kpi.detail ? (
          <Text size="xs" c="dimmed">
            {kpi.detail}
          </Text>
        ) : null}
        {kpi.sparkline?.length ? <MiniSparkline points={kpi.sparkline} /> : null}
        {delta ? (
          <Badge size="sm" variant="light" color={deltaColor} data-testid="kpi-delta">
            {delta.value > 0 ? "▲" : delta.value < 0 ? "▼" : "—"} {delta.label}
          </Badge>
        ) : null}
      </Stack>
    </Paper>
  );
}
