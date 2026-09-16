import { useEffect } from "react";
import { Alert, Button, Center, Loader, Paper, Stack, Text, Title } from "@mantine/core";
import { useNavigate } from "react-router-dom";

import { useDemoStatus } from "@/api/demo";

/**
 * The URL the landing page's "Try the demo" link points at.
 *
 * There is no one-click session mint any more — `POST /api/demo/session` is
 * gone, along with the shared `demo`/`demo` password. This route only reads
 * `/api/demo/status` and routes the visitor to wherever their access actually
 * is: the email sign-in form, the dashboard, or the "time's up" page. A
 * deployment where `DEMO_MODE` is off has no demo to route into, so it falls
 * back to the real sign-in gate instead of leaving a stranger on a dead page.
 */
export function DemoEntry() {
  const navigate = useNavigate();
  const demo = useDemoStatus();

  useEffect(() => {
    if (!demo.data || !demo.data.enabled) {
      return;
    }
    if (demo.data.access?.gate === false) {
      navigate("/", { replace: true });
      return;
    }
    const accessStatus = demo.data.access?.status;
    if (accessStatus === "active") {
      navigate("/", { replace: true });
    } else if (accessStatus === "ended" || accessStatus === "revoked") {
      navigate("/access/ended", { replace: true });
    } else {
      navigate("/access", { replace: true });
    }
  }, [demo.data, navigate]);

  if (demo.data && !demo.data.enabled) {
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
