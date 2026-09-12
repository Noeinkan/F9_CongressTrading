import { useEffect, useRef, useState } from "react";
import { Alert, Button, Center, Loader, Paper, Stack, Text, Title } from "@mantine/core";
import { Navigate, useNavigate } from "react-router-dom";

import { useSessionProbe } from "@/api/auth";
import { useDemoSignIn, useDemoStatus } from "@/api/demo";

/**
 * The door the landing page's "Try the demo" link opens.
 *
 * Mints the demo session server-side and drops the visitor on the dashboard, so
 * the demo is one click from noeinsolutions.com. The login gate is untouched:
 * anyone arriving at the root URL still meets it, and this route is dead on a
 * deployment where `DEMO_MODE` is off — `POST /api/demo/session` 404s there,
 * and the visitor is sent to the normal sign-in form.
 */
export function DemoEntry() {
  const navigate = useNavigate();
  const session = useSessionProbe();
  const demo = useDemoStatus();
  const signIn = useDemoSignIn();
  const [failed, setFailed] = useState(false);
  const attempted = useRef(false);

  const alreadyIn =
    session.data && (!session.data.auth_required || session.data.authenticated);

  useEffect(() => {
    if (attempted.current || alreadyIn || !demo.data) {
      return;
    }
    if (!demo.data.enabled) {
      setFailed(true);
      return;
    }
    attempted.current = true;
    signIn
      .mutateAsync()
      .then(() => navigate("/", { replace: true }))
      .catch(() => setFailed(true));
  }, [alreadyIn, demo.data, navigate, signIn]);

  if (alreadyIn) {
    return <Navigate to="/" replace />;
  }

  // No demo on this deployment (or the mint failed): fall back to the real gate
  // rather than leaving a stranger on a dead page.
  if (failed) {
    return (
      <Center h="100vh" p="md">
        <Paper p="xl" radius="md" shadow="sm" withBorder w={420} maw="100%">
          <Stack gap="md">
            <Title order={3}>No demo here</Title>
            <Alert color="yellow" title="This deployment is not the public demo">
              The demo runs as a separate, read-only copy of the dashboard. This
              one is the real thing, so it wants a real sign-in.
            </Alert>
            <Button onClick={() => navigate("/login", { replace: true })}>
              Go to sign in
            </Button>
          </Stack>
        </Paper>
      </Center>
    );
  }

  return (
    <Center h="100vh">
      <Stack align="center" gap="sm" data-testid="demo-entry-loading">
        <Loader size="md" />
        <Text c="dimmed">Opening the demo…</Text>
      </Stack>
    </Center>
  );
}
