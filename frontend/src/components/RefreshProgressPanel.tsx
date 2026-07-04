import {
  Button,
  Group,
  Progress,
  ScrollArea,
  Stack,
  Stepper,
  Text,
} from "@mantine/core";
import { useEffect, useRef, useState } from "react";

import { formatDuration, formatEta, type RefreshStatusResponse } from "@/api/refresh";
import { downloadRefreshLog } from "@/components/RefreshLogPanel";

const PHASE_LABELS = [
  "Download House FD",
  "Ingest House",
  "Ingest Senate",
  "Download OGE",
  "Ingest OGE",
] as const;

type RefreshProgressPanelProps = {
  status: RefreshStatusResponse;
  isLive: boolean;
  variant?: "compact" | "expanded";
  showStepper?: boolean;
  showTerminalFooter?: boolean;
  failedMessage?: string | null;
  resultSummary?: {
    rowsPtr: number | null;
    rowsTotal: number | null;
    senate?: { pdfs?: number; reason?: string };
  } | null;
};

function logLineColor(line: string): string | undefined {
  if (
    line.startsWith("ERROR:") ||
    line.includes("Traceback") ||
    line.includes("✗") ||
    line.includes("Errore")
  ) {
    return "red";
  }
  if (
    line.startsWith("House FD") ||
    line.startsWith("Senate") ||
    line.startsWith("OGE") ||
    line.startsWith("PTR") ||
    line.startsWith("Nessun")
  ) {
    return "dimmed";
  }
  return undefined;
}

function useElapsedSeconds(startedAt: string | null, isLive: boolean): number | null {
  const [elapsed, setElapsed] = useState<number | null>(null);

  useEffect(() => {
    if (!startedAt) {
      setElapsed(null);
      return;
    }
    const startMs = Date.parse(startedAt);
    if (!Number.isFinite(startMs)) {
      setElapsed(null);
      return;
    }

    const tick = () => setElapsed(Math.max(0, Math.floor((Date.now() - startMs) / 1000)));
    tick();
    if (!isLive) return;
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, [startedAt, isLive]);

  return elapsed;
}

export function RefreshProgressPanel({
  status,
  isLive,
  variant = "compact",
  showStepper = false,
  showTerminalFooter = false,
  failedMessage = null,
  resultSummary = null,
}: RefreshProgressPanelProps) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const [stickToBottom, setStickToBottom] = useState(true);
  const logHeight = variant === "expanded" ? 360 : 140;
  const lines = status.log_lines.length ? status.log_lines : status.log_tail;
  const elapsedSeconds = useElapsedSeconds(status.started_at, isLive);

  useEffect(() => {
    if (!stickToBottom) return;
    const viewport = viewportRef.current;
    if (!viewport) return;
    viewport.scrollTop = viewport.scrollHeight;
  }, [lines.length, lines[lines.length - 1], stickToBottom]);

  const subLabel =
    status.sub_total > 0
      ? `${status.phase_label || status.current_step}: ${status.sub_done} of ${status.sub_total} ${status.sub_unit}`.trim()
      : status.phase_label || status.current_step;

  const activePhase = Math.min(
    Math.max(status.phase_index, 0),
    PHASE_LABELS.length - 1,
  );

  return (
    <Stack gap="xs" data-testid={variant === "expanded" ? "sidebar-refresh-popover" : "sidebar-refresh-progress-panel"}>
      {showStepper ? (
        <Stepper
          active={activePhase}
          size="xs"
          orientation="vertical"
          data-testid={`sidebar-refresh-phase-${activePhase}`}
        >
          {PHASE_LABELS.map((label, index) => (
            <Stepper.Step key={label} label={label} data-testid={`sidebar-refresh-phase-step-${index}`} />
          ))}
        </Stepper>
      ) : null}

      {isLive && status.sub_total > 0 ? (
        <Stack gap={4}>
          <Text size="xs" c="dimmed">
            {subLabel}
          </Text>
          <Progress value={status.sub_progress} size="xs" color="navy" />
        </Stack>
      ) : null}

      {isLive ? (
        <Group gap="md" justify="space-between">
          <Text size="xs" c="dimmed" data-testid="sidebar-refresh-elapsed">
            Elapsed {formatDuration(elapsedSeconds)}
          </Text>
          <Text size="xs" c="dimmed" data-testid="sidebar-refresh-eta">
            {formatEta(status.eta_seconds)}
          </Text>
        </Group>
      ) : null}

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
            onClick={() => downloadRefreshLog(lines, status.started_at)}
            data-testid="sidebar-refresh-log-download"
          >
            Download
          </Button>
        </Group>
        <ScrollArea
          h={logHeight}
          type="auto"
          offsetScrollbars
          viewportRef={viewportRef}
          onScrollPositionChange={({ y }) => {
            const viewport = viewportRef.current;
            if (!viewport) return;
            const atBottom = y + viewport.clientHeight >= viewport.scrollHeight - 24;
            setStickToBottom(atBottom);
          }}
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
                  c={logLineColor(line)}
                  style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}
                >
                  {line}
                </Text>
              ))}
            </Stack>
          )}
        </ScrollArea>
        {isLive && !stickToBottom ? (
          <Button
            variant="light"
            size="compact-xs"
            color="navy"
            onClick={() => {
              const viewport = viewportRef.current;
              if (!viewport) return;
              viewport.scrollTop = viewport.scrollHeight;
              setStickToBottom(true);
            }}
          >
            Jump to live
          </Button>
        ) : null}
      </Stack>

      {showTerminalFooter && !isLive && status.status === "succeeded" && resultSummary ? (
        <Stack gap={2} data-testid="sidebar-refresh-summary">
          {resultSummary.rowsPtr != null ? (
            <Text size="xs" c="teal">
              {resultSummary.rowsPtr} PTR rows seen across FD metadata
              {resultSummary.rowsTotal != null ? ` (${resultSummary.rowsTotal} total)` : ""}
            </Text>
          ) : null}
        </Stack>
      ) : null}
      {showTerminalFooter && !isLive && status.status === "succeeded" ? (
        <Text size="xs" c="teal" data-testid="sidebar-refresh-success">
          Refresh completed
        </Text>
      ) : null}
      {showTerminalFooter && !isLive && status.status === "failed" ? (
        <Text size="xs" c="red" data-testid="sidebar-refresh-error">
          {failedMessage ?? "Refresh failed — check server logs"}
        </Text>
      ) : null}
      {showTerminalFooter && !isLive && status.status === "cancelled" ? (
        <Text size="xs" c="dimmed" data-testid="sidebar-refresh-cancelled">
          Refresh cancelled
        </Text>
      ) : null}
    </Stack>
  );
}
