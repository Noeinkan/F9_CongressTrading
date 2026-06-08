import { Card, Stack, Text, Title } from "@mantine/core";
import type { ReactNode } from "react";

type ChartCardProps = {
  title: string;
  caption?: string;
  children: ReactNode;
  testId?: string;
  headerRight?: ReactNode;
};

export function ChartCard({ title, caption, children, testId, headerRight }: ChartCardProps) {
  return (
    <Card withBorder radius="md" padding="md" data-testid={testId}>
      <Stack gap="sm">
        <Stack gap={2}>
          <Card.Section inheritPadding py="xs">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
              <Title order={4}>{title}</Title>
              {headerRight}
            </div>
          </Card.Section>
          {caption ? (
            <Text size="sm" c="dimmed">
              {caption}
            </Text>
          ) : null}
        </Stack>
        {children}
      </Stack>
    </Card>
  );
}
