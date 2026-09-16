import { Alert, Anchor, Badge, Group, Stack, Text } from "@mantine/core";
import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { demoQueryKey, useDemoSignOut, useDemoStatus } from "@/api/demo";

const DISMISS_KEY = "f9-demo-banner-dismissed";
const RED_ZONE_MS = 5 * 60 * 1000;

/** Per-tab, not per-browser: the next visitor to this URL sees the notice again. */
function readDismissed(): boolean {
  try {
    return window.sessionStorage.getItem(DISMISS_KEY) === "1";
  } catch {
    return false;
  }
}

/** `mm:ss`, or `h:mm:ss` once the demo grants an hour or more. */
function formatCountdown(msLeft: number): string {
  const totalSeconds = Math.max(0, Math.round(msLeft / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  const mm = String(minutes).padStart(2, "0");
  const ss = String(seconds).padStart(2, "0");
  return hours > 0 ? `${hours}:${mm}:${ss}` : `${minutes}:${ss}`;
}

/**
 * The honesty line: this is a demo, the data is frozen, nothing here can be
 * changed — plus, once the access gate is on, the countdown to when that
 * stops being true.
 *
 * Renders nothing on a normal deployment — `/api/demo/status` answers
 * `{ enabled: false }` and this returns null before any layout is affected.
 *
 * The countdown never polls the server: `expiresAt` and `serverNow` are read
 * once from the status fetch, the gap between `serverNow` and this browser's
 * clock is captured as an offset, and a local `setInterval` ticks the display
 * against that. Dismissing hides only the notice text — the countdown and
 * "Sign out" stay on screen, because leaving the visitor unable to tell how
 * much time is left is worse than the notice being mildly repetitive.
 */
export function DemoBanner() {
  const { data } = useDemoStatus();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const signOut = useDemoSignOut();
  const [dismissed, setDismissed] = useState(readDismissed);
  const [now, setNow] = useState(() => Date.now());
  const offsetRef = useRef(0);

  const expiresAtMs = useMemo(() => {
    const raw = data?.access?.expiresAt;
    if (!raw) return null;
    const parsed = new Date(raw).getTime();
    return Number.isNaN(parsed) ? null : parsed;
  }, [data?.access?.expiresAt]);

  useEffect(() => {
    const raw = data?.access?.serverNow;
    if (!raw) return;
    const serverNowMs = new Date(raw).getTime();
    if (Number.isNaN(serverNowMs)) return;
    offsetRef.current = serverNowMs - Date.now();
  }, [data?.access?.serverNow]);

  useEffect(() => {
    if (expiresAtMs == null) return undefined;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [expiresAtMs]);

  const msLeft = expiresAtMs != null ? expiresAtMs - (now + offsetRef.current) : null;

  useEffect(() => {
    if (msLeft == null || msLeft > 0) return;
    void queryClient.invalidateQueries({ queryKey: demoQueryKey });
    navigate("/access/ended");
  }, [msLeft, navigate, queryClient]);

  const dismiss = useCallback(() => {
    setDismissed(true);
    try {
      window.sessionStorage.setItem(DISMISS_KEY, "1");
    } catch {
      // Private browsing with storage blocked: the banner just comes back on reload.
    }
  }, []);

  const handleSignOut = useCallback(() => {
    void signOut.mutateAsync().finally(() => {
      void queryClient.invalidateQueries({ queryKey: demoQueryKey });
      navigate("/access", { replace: true });
    });
  }, [signOut, queryClient, navigate]);

  if (!data?.enabled) {
    return null;
  }

  const gateOn = data.access?.gate === true;
  const redZone = msLeft != null && msLeft <= RED_ZONE_MS;

  return (
    <Stack gap={4} mb="md" data-testid="demo-banner-wrap">
      {!dismissed ? (
        <Alert
          color="orange"
          variant="light"
          withCloseButton
          closeButtonLabel="Dismiss the demo notice"
          onClose={dismiss}
          data-testid="demo-banner"
          title="Public demo"
        >
          <Group gap="xs" wrap="wrap">
            <Text size="sm" span>
              {data.notice}
            </Text>
            {data.snapshotLabel ? (
              <Text size="sm" fw={600} span data-testid="demo-banner-snapshot">
                {data.snapshotLabel} — it does not refresh.
              </Text>
            ) : null}
            {data.sourceUrl ? (
              <Anchor size="sm" href={data.sourceUrl} target="_blank" rel="noopener">
                About this build
              </Anchor>
            ) : null}
          </Group>
        </Alert>
      ) : null}
      {gateOn ? (
        <Group gap="sm" wrap="wrap" data-testid="demo-countdown-bar">
          {msLeft != null ? (
            <Badge
              color={redZone ? "red" : "gray"}
              variant={redZone ? "filled" : "light"}
              data-testid="demo-countdown"
              data-red-zone={redZone ? "true" : "false"}
            >
              {formatCountdown(msLeft)} left
            </Badge>
          ) : null}
          {data.access?.address ? (
            <Text size="sm" c="dimmed" data-testid="demo-banner-identity">
              Signed in as {data.access.address} ·{" "}
              <Anchor
                component="button"
                type="button"
                size="sm"
                onClick={handleSignOut}
                data-testid="demo-banner-signout"
              >
                Sign out
              </Anchor>
            </Text>
          ) : null}
        </Group>
      ) : null}
    </Stack>
  );
}
