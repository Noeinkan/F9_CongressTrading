import { Component, type ErrorInfo, type ReactNode } from "react";
import { Alert, Button, Stack, Text, Title } from "@mantine/core";

type Props = {
  children: ReactNode;
};

type State = {
  error: Error | null;
};

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("Unhandled render error", error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <Stack p="xl" gap="md">
          <Title order={3}>Something went wrong</Title>
          <Alert color="red" title="Render error">
            <Text size="sm">{this.state.error.message}</Text>
          </Alert>
          <Button onClick={() => this.setState({ error: null })}>Try again</Button>
        </Stack>
      );
    }
    return this.props.children;
  }
}
