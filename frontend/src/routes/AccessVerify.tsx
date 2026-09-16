import { Alert, Button, Center, Loader, Paper, Stack, Text, Title } from "@mantine/core";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { ApiError } from "@/api/client";
import { demoQueryKey, useDemoAccessLinkConfirm, useDemoAccessLinkInfo } from "@/api/demo";

function ExpiredCard() {
  return (
    <Center h="100vh" p="md">
      <Paper p="xl" radius="md" shadow="sm" withBorder w={420} maw="100%">
        <Stack gap="md" data-testid="access-verify-expired">
          <Title order={3}>That link has expired</Title>
          <Text c="dimmed" size="sm">
            Sign-in links work once, for a few minutes.
          </Text>
          <Button component={Link} to="/access" data-testid="access-verify-retry">
            Ask for a new code
          </Button>
        </Stack>
      </Paper>
    </Center>
  );
}

/**
 * Landed on from the emailed link (`/access/verify?t=…`).
 *
 * The GET on load (`useDemoAccessLinkInfo`) only looks the token up — it must
 * never spend it, because corporate mail scanners open links automatically
 * before a person ever sees the message. Only the explicit button click below
 * spends it, with a real POST.
 */
export function AccessVerify() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("t");
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const linkInfo = useDemoAccessLinkInfo(token);
  const confirm = useDemoAccessLinkConfirm();
  const [error, setError] = useState<{ detail: string; dead?: boolean } | null>(null);

  const handleContinue = async () => {
    if (!token) return;
    setError(null);
    try {
      await confirm.mutateAsync(token);
      void queryClient.invalidateQueries({ queryKey: demoQueryKey });
      navigate("/", { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        const body = err.body && typeof err.body === "object" ? (err.body as Record<string, unknown>) : null;
        const code = body?.code;
        const detail = typeof body?.detail === "string" ? body.detail : "This link no longer works.";
        if (code === "LINK_DEAD") {
          setError({ detail, dead: true });
          return;
        }
        if (code === "DEMO_EXPIRED") {
          navigate("/access/ended");
          return;
        }
        setError({ detail });
        return;
      }
      setError({ detail: "This link no longer works." });
    }
  };

  if (!token) {
    return <ExpiredCard />;
  }

  if (linkInfo.isLoading) {
    return (
      <Center h="100vh">
        <Stack align="center" gap="sm" data-testid="access-verify-loading">
          <Loader size="md" />
          <Text c="dimmed">Checking your link…</Text>
        </Stack>
      </Center>
    );
  }

  if (linkInfo.isError) {
    return <ExpiredCard />;
  }

  return (
    <Center h="100vh" p="md">
      <Paper p="xl" radius="md" shadow="sm" withBorder w={420} maw="100%">
        <Stack gap="md" data-testid="access-verify-confirm">
          <Title order={3}>Continue as {linkInfo.data?.address}</Title>
          {error ? (
            <Alert color="red" title="That didn't work" data-testid="access-verify-error">
              <Stack gap={4}>
                <Text size="sm">{error.detail}</Text>
                {error.dead ? (
                  <Button
                    component={Link}
                    to="/access"
                    size="xs"
                    variant="light"
                    data-testid="access-verify-error-retry"
                  >
                    Ask for a new code
                  </Button>
                ) : null}
              </Stack>
            </Alert>
          ) : null}
          <Button
            onClick={() => void handleContinue()}
            loading={confirm.isPending}
            data-testid="access-verify-continue"
          >
            Continue
          </Button>
        </Stack>
      </Paper>
    </Center>
  );
}
