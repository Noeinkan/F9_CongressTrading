import { Paper, Stack, Text, Title } from "@mantine/core";

import type { SparklinePoint } from "@/api/types";
import { MiniSparkline } from "./MiniSparkline";

export type KpiTileSimpleSpec = {
  key: string;
  label: string;
  value: string | number;
  detail?: string;
  sparkline?: SparklinePoint[];
};

type KpiTileSimpleProps = {
  kpi: KpiTileSimpleSpec;
};

export function KpiTileSimple({ kpi }: KpiTileSimpleProps) {
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
      </Stack>
    </Paper>
  );
}
