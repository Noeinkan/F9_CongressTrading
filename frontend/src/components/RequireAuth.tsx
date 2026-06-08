import { useEffect, useState } from "react";
import { Alert, Button, Center, Loader, Stack, Text } from "@mantine/core";
import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useSessionProbe } from "@/api/auth";

const SESSION_PROBE_TIMEOUT_MS = 5_000;

export function RequireAuth() {
  const location = useLocation();
  const session = useSessionProbe();
  const [timedOut, setTimedOut] = useState(false);

  // Surface a clear error if `/api/session` hangs (e.g. API server is down)
  // instead of leaving the user staring at a spinner forever.
  useEffect(() => {
    if (!session.isLoading) {
      setTimedOut(false);
      return;
    }
    const id = window.setTimeout(() => setTimedOut(true), SESSION_PROBE_TIMEOUT_MS);
    return () => window.clearTimeout(id);
  }, [session.isLoading, session.isFetching]);

  if (session.isLoading && !timedOut) {
    return (
      <Center h="100vh">
        <Stack align="center" gap="sm">
          <Loader size="md" />
          <Text c="dimmed">Checking session…</Text>
        </Stack>
      </Center>
    );
  }

  if (timedOut) {
    return (
      <Center h="100vh" p="md">
        <Stack align="center" gap="md" maw={420}>
          <Alert color="red" title="Session probe timed out">
            The dashboard could not reach <code>/api/session</code> within{" "}
            {SESSION_PROBE_TIMEOUT_MS / 1000}s. Make sure the FastAPI server is
            running on port 8000.
          </Alert>
          <Button onClick={() => session.refetch()}>Try again</Button>
        </Stack>
      </Center>
    );
  }

  if (session.isError) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  const data = session.data;
  if (!data) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  if (!data.auth_required || data.authenticated) {
    return <Outlet />;
  }

  return <Navigate to="/login" replace state={{ from: location }} />;
}
