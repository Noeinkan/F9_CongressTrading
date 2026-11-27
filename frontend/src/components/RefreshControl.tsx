import { Box, Button, Group, Popover, Progress, Stack, Text, Tooltip } from "@mantine/core";
import { useEffect, useState } from "react";

import { ApiError } from "@/api/client";
import {
  readRefreshExpanded,
  useCancelRefresh,
  useRefreshStatus,
  useStartRefresh,
  writeRefreshExpanded,
  type RefreshStatusResponse,
} from "@/api/refresh";
import { RefreshProgressPanel } from "@/components/RefreshProgressPanel";
import { telegramSummary } from "@/components/TelegramRefreshSummary";
import { useIsMobile } from "@/hooks/useMediaQuery";

function refreshErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const detail = error.body;
    if (typeof detail === "object" && detail !== null && "detail" in detail) {
      const message = (detail as { detail?: unknown }).detail;
      if (typeof message === "string") return message;
    }
    return error.message;
  }
  if (error instanceof Error) return error.message;
  return "Refresh request failed";
}

function buildResultSummary(result: Record<string, unknown> | undefined) {
  if (!result || typeof result !== "object") return null;
  const rowsPtr = typeof result.house_fd_rows_ptr === "number" ? result.house_fd_rows_ptr : null;
  const rowsTotal = typeof result.house_fd_rows_total === "number" ? result.house_fd_rows_total : null;
  const senate = (result as { senate?: { pdfs?: number; reason?: string } }).senate;
  const telegram = telegramSummary(result.post_ingest);
  if (rowsPtr == null && rowsTotal == null && !senate && !telegram) return null;
  return { rowsPtr, rowsTotal, senate, telegram };
}

function normalizeRefreshStatus(
  data: Partial<RefreshStatusResponse> | undefined,
): RefreshStatusResponse {
  return {
    status: data?.status ?? "idle",
    started_at: data?.started_at ?? null,
    finished_at: data?.finished_at ?? null,
    current_step: data?.current_step ?? "",
    progress: data?.progress ?? 0,
    phase_label: data?.phase_label ?? "",
    phase_index: data?.phase_index ?? 0,
    phase_total: data?.phase_total ?? 6,
    sub_progress: data?.sub_progress ?? 0,
    sub_done: data?.sub_done ?? 0,
    sub_total: data?.sub_total ?? 0,
    sub_unit: data?.sub_unit ?? "",
    eta_seconds: data?.eta_seconds ?? null,
    step_started_at: data?.step_started_at ?? null,
    log_tail: data?.log_tail ?? [],
    log_lines: data?.log_lines ?? data?.log_tail ?? [],
    result: data?.result ?? {},
  };
}

function finishedLabel(finishedAt: string | null): string {
  if (!finishedAt) return "Updated";
  const ms = Date.parse(finishedAt);
  if (!Number.isFinite(ms)) return "Updated";
  const when = new Date(ms);
  const sameDay = when.toDateString() === new Date().toDateString();
  const time = when.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  return sameDay ? `Updated ${time}` : `Updated ${when.toLocaleDateString()} ${time}`;
}

/**
 * Admin refresh in the top bar: one button plus a one-line status that opens
 * the full progress panel (stepper, live log, Telegram outcome) in a popover.
 */
export function RefreshControl() {
  const refreshStatus = useRefreshStatus();
  const startRefresh = useStartRefresh();
  const cancelRefresh = useCancelRefresh();
  const isMobile = useIsMobile();

  const refreshData = normalizeRefreshStatus(refreshStatus.data);
  const status = refreshData.status;
  const isRunning = status === "running" || startRefresh.isPending;
  const progress = refreshData.progress;
  const failedMessage =
    typeof refreshData.result?.error === "string" ? refreshData.result.error : null;
  const resultSummary = buildResultSummary(refreshData.result);
  const hasDetails =
    isRunning ||
    (status !== "idle" && (refreshData.log_lines.length > 0 || Boolean(refreshData.started_at)));

  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (!refreshData.started_at) return;
    setExpanded(readRefreshExpanded(refreshData.started_at));
  }, [refreshData.started_at]);

  const setExpandedPersisted = (next: boolean) => {
    setExpanded(next);
    writeRefreshExpanded(refreshData.started_at, next);
  };

  const buttonLabel = isRunning
    ? isMobile
      ? `${progress}%`
      : `Refreshing… ${progress}%`
    : status === "failed" || status === "cancelled"
      ? "Retry refresh"
      : isMobile
        ? "Refresh"
        : "Refresh data";

  let statusText: string | null = null;
  let statusColor = "dimmed";
  if (startRefresh.isError && !isRunning) {
    statusText = refreshErrorMessage(startRefresh.error);
    statusColor = "red";
  } else if (isRunning) {
    statusText = refreshData.phase_label || refreshData.current_step || "Starting…";
    statusColor = "navy";
  } else if (status === "succeeded") {
    statusText = finishedLabel(refreshData.finished_at);
    statusColor = "teal";
  } else if (status === "failed") {
    statusText = failedMessage ?? "Refresh failed";
    statusColor = "red";
  } else if (status === "cancelled") {
    statusText = "Refresh cancelled";
  }

  return (
    <Group gap={6} wrap="nowrap" data-testid="topbar-refresh">
      <Tooltip
        label="Incremental refresh: re-fetch this year's House FD catalog from the Clerk, download only missing PTR PDFs, and parse only filings not yet ingested. Then sends Telegram alerts for new trades and the weekly digest — the digest is skipped if one already went out in the last 12 hours."
        multiline
        w={280}
        openDelay={400}
      >
        <Button
          color="navy"
          variant={isRunning ? "light" : "filled"}
          size="compact-sm"
          disabled={isRunning || cancelRefresh.isPending}
          onClick={() => startRefresh.mutate()}
          data-testid="sidebar-refresh"
        >
          {buttonLabel}
        </Button>
      </Tooltip>

      {statusText ? (
        <Popover
          opened={expanded}
          onChange={setExpandedPersisted}
          position="bottom-end"
          width={520}
          withArrow
          shadow="md"
          trapFocus={false}
        >
          <Popover.Target>
            <Button
              variant="subtle"
              color={statusColor === "dimmed" ? "gray" : statusColor}
              size="compact-xs"
              onClick={() => setExpandedPersisted(!expanded)}
              disabled={!hasDetails && !startRefresh.isError}
              aria-label={`Refresh status: ${statusText}. Show details`}
              data-testid="sidebar-refresh-expand"
              styles={{ label: { overflow: "hidden", textOverflow: "ellipsis" } }}
              maw={isMobile ? 28 : 220}
              px={6}
            >
              {isMobile ? (
                <Box
                  w={8}
                  h={8}
                  bg={statusColor === "dimmed" ? "gray.5" : `${statusColor}.6`}
                  style={{ borderRadius: "50%" }}
                />
              ) : (
                <Text span size="xs" c={statusColor} truncate data-testid="topbar-refresh-status">
                  {statusText}
                </Text>
              )}
            </Button>
          </Popover.Target>
          <Popover.Dropdown p="sm">
            <Stack gap="xs">
              {isRunning ? (
                <Group gap="xs" wrap="nowrap">
                  <Progress
                    value={progress}
                    size="sm"
                    color="navy"
                    style={{ flex: 1 }}
                    data-testid="sidebar-refresh-progress"
                  />
                  <Button
                    variant="subtle"
                    color="red"
                    size="compact-xs"
                    loading={cancelRefresh.isPending}
                    disabled={startRefresh.isPending}
                    onClick={() => cancelRefresh.mutate()}
                    data-testid="sidebar-refresh-cancel"
                  >
                    Cancel
                  </Button>
                </Group>
              ) : null}
              {hasDetails ? (
                <RefreshProgressPanel
                  status={refreshData}
                  isLive={isRunning}
                  variant="expanded"
                  showStepper
                  showTerminalFooter
                  failedMessage={failedMessage}
                  resultSummary={resultSummary}
                />
              ) : null}
              {startRefresh.isError ? (
                <Text size="xs" c="red" data-testid="sidebar-refresh-start-error">
                  {refreshErrorMessage(startRefresh.error)}
                </Text>
              ) : null}
            </Stack>
          </Popover.Dropdown>
        </Popover>
      ) : null}
    </Group>
  );
}
