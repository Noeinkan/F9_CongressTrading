import { Alert, Anchor, Group, Text } from "@mantine/core";
import { useCallback, useState } from "react";

import { useDemoStatus } from "@/api/demo";

const DISMISS_KEY = "f9-demo-banner-dismissed";

/** Per-tab, not per-browser: the next visitor to this URL sees the notice again. */
function readDismissed(): boolean {
  try {
    return window.sessionStorage.getItem(DISMISS_KEY) === "1";
  } catch {
    return false;
  }
}

/**
 * The honesty line: this is a demo, the data is frozen, nothing here can be changed.
 *
 * Renders nothing on a normal deployment — `/api/demo/status` answers
 * `{ enabled: false }` and this returns null before any layout is affected.
 */
export function DemoBanner() {
  const { data } = useDemoStatus();
  const [dismissed, setDismissed] = useState(readDismissed);

  const dismiss = useCallback(() => {
    setDismissed(true);
    try {
      window.sessionStorage.setItem(DISMISS_KEY, "1");
    } catch {
      // Private browsing with storage blocked: the banner just comes back on reload.
    }
  }, []);

  if (!data?.enabled || dismissed) {
    return null;
  }

  return (
    <Alert
      color="orange"
      variant="light"
      withCloseButton
      closeButtonLabel="Dismiss the demo notice"
      onClose={dismiss}
      mb="md"
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
  );
}
