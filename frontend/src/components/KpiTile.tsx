import { Badge, Paper, Stack, Text, Title } from "@mantine/core";

import type { KpiDelta, SparklinePoint } from "@/api/types";

import { MiniSparkline } from "./MiniSparkline";

export type KpiTileSpec = {
  key: string;
  label: string;
  value: string | number;
  detail?: string;
  sparkline?: Array<SparklinePoint | number>;
  delta?: KpiDelta | string | null;
};

type KpiTileProps = {
  kpi: KpiTileSpec;
  compact?: boolean;
};

export function KpiTile({ kpi, compact = false }: KpiTileProps) {
  const delta = typeof kpi.delta === "string" ? null : kpi.delta;
  const deltaColor = delta
    ? delta.value > 0
      ? "teal"
      : delta.value < 0
        ? "red"
        : "gray"
    : "gray";

  return (
    // Tiles sit two per row on a phone: tighter padding there, and long values
    // or delta labels wrap instead of being cut off with an ellipsis.
    <Paper p={compact ? "sm" : { base: "sm", sm: "md" }} radius="md" withBorder data-testid={`kpi-tile-${kpi.key}`}>
      <Stack gap={6}>
        <Text size="xs" c="dimmed" tt="uppercase" fw={700}>
          {kpi.label}
        </Text>
        <Title order={3} style={{ overflowWrap: "anywhere" }}>
          {typeof kpi.value === "number" ? kpi.value.toLocaleString() : kpi.value}
        </Title>
        {kpi.detail ? (
          <Text size="xs" c="dimmed">
            {kpi.detail}
          </Text>
        ) : null}
        {kpi.sparkline?.length ? (
          <MiniSparkline points={kpi.sparkline} height={compact ? 24 : undefined} />
        ) : null}
        {typeof kpi.delta === "string" ? (
          <Text size="xs" c="dimmed" data-testid="kpi-delta">{kpi.delta}</Text>
        ) : null}
        {delta ? (
          <Badge
            size="sm"
            variant="light"
            color={deltaColor}
            data-testid="kpi-delta"
            styles={{ root: { height: "auto", maxWidth: "100%" }, label: { whiteSpace: "normal" } }}
          >
            {delta.value > 0 ? "▲" : delta.value < 0 ? "▼" : "—"} {delta.label}
          </Badge>
        ) : null}
      </Stack>
    </Paper>
  );
}
