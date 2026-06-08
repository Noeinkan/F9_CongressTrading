import { Button, Group, ScrollArea, Stack, Text } from "@mantine/core";
import { useEffect, useRef } from "react";

type RefreshLogPanelProps = {
  lines: string[];
  startedAt: string | null;
  isLive: boolean;
};

function logFilename(startedAt: string | null): string {
  const stamp = startedAt
    ? startedAt.replace(/[:.]/g, "-").slice(0, 19)
    : new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
  return `refresh-log-${stamp}.txt`;
}

export function downloadRefreshLog(lines: string[], startedAt: string | null): void {
  const body = lines.length ? lines.join("\n") : "(no log output)";
  const blob = new Blob([`${body}\n`], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = logFilename(startedAt);
  anchor.click();
  URL.revokeObjectURL(url);
}

export function RefreshLogPanel({ lines, startedAt, isLive }: RefreshLogPanelProps) {
  const viewportRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    viewport.scrollTop = viewport.scrollHeight;
  }, [lines.length, lines[lines.length - 1]]);

  return (
    <Stack gap={4} data-testid="sidebar-refresh-log">
      <Group justify="space-between" gap="xs">
        <Text size="xs" c="dimmed" fw={600}>
          {isLive ? "Live log" : "Log"}
        </Text>
        <Button
          variant="subtle"
          size="compact-xs"
          color="navy"
          disabled={lines.length === 0}
          onClick={() => downloadRefreshLog(lines, startedAt)}
          data-testid="sidebar-refresh-log-download"
        >
          Download
        </Button>
      </Group>
      <ScrollArea
        h={140}
        type="auto"
        offsetScrollbars
        viewportRef={viewportRef}
        styles={{
          root: {
            border: "1px solid var(--mantine-color-gray-3)",
            borderRadius: "var(--mantine-radius-sm)",
            backgroundColor: "var(--mantine-color-gray-0)",
          },
        }}
      >
        {lines.length === 0 ? (
          <Text size="xs" c="dimmed" p="xs" ff="monospace">
            Waiting for output…
          </Text>
        ) : (
          <Stack gap={0} p="xs">
            {lines.map((line, index) => (
              <Text
                key={`${index}-${line.slice(0, 24)}`}
                size="xs"
                ff="monospace"
                lh={1.35}
                style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}
              >
                {line}
              </Text>
            ))}
          </Stack>
        )}
      </ScrollArea>
    </Stack>
  );
}
