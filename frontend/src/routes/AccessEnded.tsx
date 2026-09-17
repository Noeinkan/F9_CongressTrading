import { Anchor, Button, Center, Paper, Stack, Text, Title } from "@mantine/core";
import { useQueryClient } from "@tanstack/react-query";
import { Navigate, useNavigate } from "react-router-dom";

import { demoQueryKey, useDemoSignOut, useDemoStatus } from "@/api/demo";

/**
 * Where every ended or revoked demo session lands, and the only place it can
 * go from here — there is deliberately no "start a new session" button. A
 * visitor who wants more gets pointed at a human, not a way to reset the
 * clock.
 */
export function AccessEnded() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const status = useDemoStatus();
  const signOut = useDemoSignOut();

  const access = status.data?.access;
  const revoked = access?.status === "revoked";
  const minutes = status.data?.session?.minutes ?? 45;
  const contactEmail = status.data?.contactEmail;

  // Back in only when the server says there is real time left (the owner granted
  // more): a second of clock skew at zero must not bounce the visitor back and forth.
  const secondsLeft =
    access?.status === "active" && access.expiresAt && access.serverNow
      ? (new Date(access.expiresAt).getTime() - new Date(access.serverNow).getTime()) / 1000
      : 0;
  if (secondsLeft > 5) {
    return <Navigate to="/" replace />;
  }

  const handleSignOut = async () => {
    try {
      await signOut.mutateAsync();
    } finally {
      void queryClient.invalidateQueries({ queryKey: demoQueryKey });
      navigate("/access", { replace: true });
    }
  };

  return (
    <Center h="100vh" p="md">
      <Paper p="xl" radius="md" shadow="sm" withBorder w={440} maw="100%">
        <Stack gap="md" data-testid="access-ended-page">
          <Title order={3}>
            {revoked
              ? "Your demo access has been switched off"
              : `Your ${minutes} minutes with the demo are up`}
          </Title>
          <Text c="dimmed" size="sm">
            You saw House and Senate disclosures, members, tickers and trading patterns, frozen at the
            snapshot date.
          </Text>
          {contactEmail ? (
            <Button
              component="a"
              href={`mailto:${contactEmail}`}
              data-testid="access-ended-contact"
            >
              Get in touch for full access
            </Button>
          ) : null}
          <Anchor
            size="sm"
            c="dimmed"
            onClick={() => void handleSignOut()}
            data-testid="access-ended-signout"
          >
            Sign out
          </Anchor>
        </Stack>
      </Paper>
    </Center>
  );
}
