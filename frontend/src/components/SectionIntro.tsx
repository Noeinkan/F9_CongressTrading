import { Paper, Stack, Text, Title } from "@mantine/core";

type SectionIntroProps = {
  kicker: string;
  title: string;
  copy?: string;
};

export function SectionIntro({ kicker, title, copy }: SectionIntroProps) {
  return (
    <Paper p="md" radius="md" withBorder data-testid="section-intro">
      <Stack gap={4}>
        <Text size="xs" c="dimmed" tt="uppercase" fw={700}>
          {kicker}
        </Text>
        <Title order={2}>{title}</Title>
        {copy ? (
          <Text c="dimmed" size="sm">
            {copy}
          </Text>
        ) : null}
      </Stack>
    </Paper>
  );
}
