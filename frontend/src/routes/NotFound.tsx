import { Button, Stack, Text, Title } from "@mantine/core";
import { Link } from "react-router-dom";

export function NotFound() {
  return (
    <Stack p="xl" gap="md">
      <Title order={2}>Page not found</Title>
      <Text c="dimmed">The page you requested does not exist.</Text>
      <Button component={Link} to="/" variant="light">
        Back to Home
      </Button>
    </Stack>
  );
}
