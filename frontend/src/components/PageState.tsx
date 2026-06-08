import { Alert, Loader, Stack, Text } from "@mantine/core";

type PageStateProps = {
  isLoading: boolean;
  isError: boolean;
  ready?: boolean;
  emptyMessage?: string;
  children: React.ReactNode;
};

export function PageState({
  isLoading,
  isError,
  ready = true,
  emptyMessage = "No data for the selected period.",
  children,
}: PageStateProps) {
  if (isLoading) {
    return (
      <Stack align="center" py="xl" data-testid="page-loading">
        <Loader size="md" />
        <Text size="sm" c="dimmed">
          Loading…
        </Text>
      </Stack>
    );
  }
  if (isError) {
    return (
      <Alert color="red" title="Failed to load data" data-testid="page-error">
        Check that the API is running and you are signed in.
      </Alert>
    );
  }
  if (!ready) {
    return (
      <Alert color="yellow" title="No data loaded" data-testid="page-empty">
        {emptyMessage} Run ingestion first.
      </Alert>
    );
  }
  return <>{children}</>;
}
