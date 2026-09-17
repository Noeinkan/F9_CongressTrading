import { Anchor, Button, Group, Modal, Stack, Text } from "@mantine/core";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { onDemoRefusal, type DemoRefusalBody } from "@/api/client";
import { demoQueryKey, useDemoStatus } from "@/api/demo";

type WallState = {
  title: string;
  message: string;
};

function refusalDetail(body: DemoRefusalBody): string {
  if (typeof body.detail === "string" && body.detail) return body.detail;
  if (typeof body.message === "string" && body.message) return body.message;
  return "This isn't available in the public demo.";
}

/**
 * The single place every demo refusal ends up.
 *
 * `apiFetch` broadcasts a `DEMO_*` code whenever the server refuses a call
 * (session gone, time's up, a locked feature, a write the demo backstops
 * read-only); `useDemoLock` broadcasts the same shape client-side, before a
 * doomed request is even sent. Either way this is the only component that
 * turns that into UI — a redirect for the two "you're not in" cases, a modal
 * for the two "not in the demo" cases — so nobody ever sees a raw error or a
 * login page for a demo-specific refusal.
 *
 * Mount once, inside the router (e.g. in `SidebarLayout`): the calls this
 * reacts to only ever happen behind `RequireAuth`.
 */
export function DemoWall() {
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const { data } = useDemoStatus();
  const [wall, setWall] = useState<WallState | null>(null);

  useEffect(() => {
    return onDemoRefusal((body) => {
      switch (body.code) {
        case "DEMO_SIGNED_OUT": {
          void queryClient.invalidateQueries({ queryKey: demoQueryKey });
          const next = `${location.pathname}${location.search}`;
          navigate(`/access?next=${encodeURIComponent(next)}`);
          break;
        }
        case "DEMO_EXPIRED": {
          void queryClient.invalidateQueries({ queryKey: demoQueryKey });
          navigate("/access/ended");
          break;
        }
        case "DEMO_LOCKED": {
          const entry = data?.locked?.find((item) => item.feature === body.feature);
          // Lead with what the visitor reached, not with what is forbidden.
          setWall({
            title: entry ? entry.label : "Part of the full product",
            message: refusalDetail(body),
          });
          break;
        }
        case "DEMO_READ_ONLY": {
          setWall({
            title: "Read-only demo",
            message: refusalDetail(body),
          });
          break;
        }
      }
    });
  }, [navigate, location.pathname, location.search, queryClient, data?.locked]);

  const contactEmail = data?.contactEmail;

  return (
    <Modal
      opened={wall != null}
      onClose={() => setWall(null)}
      title={wall?.title}
      centered
      data-testid="demo-wall-modal"
    >
      <Stack gap="sm">
        <Text data-testid="demo-wall-message">{wall?.message}</Text>
        <Text size="sm" c="dimmed">
          Available with full access.
        </Text>
        <Group justify="flex-end">
          {contactEmail ? (
            <Anchor
              component="a"
              href={`mailto:${contactEmail}`}
              size="sm"
              data-testid="demo-wall-contact"
            >
              {contactEmail}
            </Anchor>
          ) : null}
          <Button size="xs" variant="light" onClick={() => setWall(null)}>
            Close
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
