import { Paper, Stack, Text, Title } from "@mantine/core";

type PageStubProps = {
  title: string;
  description: string;
};

export function PageStub({ title, description }: PageStubProps) {
  return (
    <Paper p="xl" radius="md" shadow="xs" withBorder>
      <Stack gap="sm">
        <Title order={2}>{title}</Title>
        <Text c="dimmed">{description}</Text>
        <Text size="sm" c="navy.6" fw={500}>
          Page implementation deferred to Phase 4.
        </Text>
      </Stack>
    </Paper>
  );
}
