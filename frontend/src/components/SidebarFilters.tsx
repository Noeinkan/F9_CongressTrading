import { Button, Divider, Group, Popover, Progress, Select, Stack, Text, Tooltip } from "@mantine/core";
import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";

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

import {
  LOOKBACK_OPTIONS,
  QUARTER_VALUES,
  useFilters,
  type QuarterValue,
} from "./FilterContext";
import { NAV_ITEMS, isActive } from "./TopBar";

const QUARTER_LABELS: Record<QuarterValue, string> = {
  "1": "Q1",
  "2": "Q2",
  "3": "Q3",
  "4": "Q4",
};

const QUARTER_DATA = QUARTER_VALUES.map((value) => ({
  value,
  label: QUARTER_LABELS[value],
}));

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
  if (rowsPtr == null && rowsTotal == null && !senate) return null;
  return { rowsPtr, rowsTotal, senate };
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
    phase_total: data?.phase_total ?? 5,
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

function SidebarRefreshControls() {
  const refreshStatus = useRefreshStatus();
  const startRefresh = useStartRefresh();
  const cancelRefresh = useCancelRefresh();

  const status = refreshStatus.data?.status ?? "idle";
  const isRunning = status === "running" || startRefresh.isPending;
  const refreshData = normalizeRefreshStatus(refreshStatus.data);
  const progress = refreshData.progress;
  const currentStep = refreshData.current_step;
  const failedMessage =
    typeof refreshData.result?.error === "string" ? refreshData.result.error : null;
  const showLogPanel =
    isRunning ||
    (status !== "idle" && (refreshData.log_lines.length > 0 || Boolean(refreshData.started_at)));
  const resultSummary = buildResultSummary(refreshData.result);

  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (!refreshData.started_at) return;
    setExpanded(readRefreshExpanded(refreshData.started_at));
  }, [refreshData.started_at]);

  const setExpandedPersisted = (next: boolean) => {
    setExpanded(next);
    writeRefreshExpanded(refreshData.started_at, next);
  };

  const primaryLabel = isRunning
    ? `Restart (${progress}%${currentStep ? ` — ${currentStep}` : ""})`
    : status === "failed" || status === "cancelled"
      ? "Retry refresh"
      : "Refresh data";

  return (
    <Tooltip
      label="Re-run the full ingest pipeline: pull House FD metadata from the Clerk, re-parse every PDF on disk (force re-parse), then ingest Senate. Use this when the dashboard is missing recent filings or after a parser/ticker update."
      multiline
      w={260}
    >
      <Stack gap="xs" data-testid="sidebar-admin">
        <Button
          color="navy"
          variant={isRunning ? "light" : "filled"}
          size="compact-sm"
          loading={isRunning}
          disabled={cancelRefresh.isPending}
          onClick={() => startRefresh.mutate()}
          data-testid="sidebar-refresh"
        >
          {isRunning ? `Refreshing… ${progress}%` : primaryLabel}
        </Button>
        {isRunning ? (
          <>
            <Progress value={progress} size="sm" color="navy" data-testid="sidebar-refresh-progress" />
            {currentStep || refreshData.phase_label ? (
              <Text size="xs" c="dimmed">
                {refreshData.phase_label || currentStep}
              </Text>
            ) : null}
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
          </>
        ) : null}
        {showLogPanel ? (
          <>
            <Group justify="flex-end">
              <Popover
                opened={expanded}
                onChange={setExpandedPersisted}
                position="right-start"
                width={520}
                withArrow
                shadow="md"
                trapFocus={false}
              >
                <Popover.Target>
                  <Button
                    variant="subtle"
                    size="compact-xs"
                    color="navy"
                    onClick={() => setExpandedPersisted(!expanded)}
                    data-testid="sidebar-refresh-expand"
                  >
                    {expanded ? "Collapse" : "Expand"}
                  </Button>
                </Popover.Target>
                <Popover.Dropdown p="sm">
                  <RefreshProgressPanel
                    status={refreshData}
                    isLive={isRunning}
                    variant="expanded"
                    showStepper
                    showTerminalFooter
                    failedMessage={failedMessage}
                    resultSummary={resultSummary}
                  />
                </Popover.Dropdown>
              </Popover>
            </Group>
            <RefreshProgressPanel status={refreshData} isLive={isRunning} variant="compact" />
          </>
        ) : null}
        {!expanded && !isRunning && status === "succeeded" && resultSummary ? (
          <Stack gap={2} data-testid="sidebar-refresh-summary">
            {resultSummary.rowsPtr != null ? (
              <Text size="xs" c="teal">
                {resultSummary.rowsPtr} PTR rows seen across FD metadata
                {resultSummary.rowsTotal != null ? ` (${resultSummary.rowsTotal} total)` : ""}
              </Text>
            ) : null}
          </Stack>
        ) : null}
        {!expanded && !isRunning && status === "succeeded" ? (
          <Text size="xs" c="teal" data-testid="sidebar-refresh-success">
            Refresh completed
          </Text>
        ) : null}
        {!expanded && !isRunning && status === "failed" ? (
          <Text size="xs" c="red" data-testid="sidebar-refresh-error">
            {failedMessage ?? "Refresh failed — check server logs"}
          </Text>
        ) : null}
        {!expanded && !isRunning && status === "cancelled" ? (
          <Text size="xs" c="dimmed" data-testid="sidebar-refresh-cancelled">
            Refresh cancelled
          </Text>
        ) : null}
        {startRefresh.isError ? (
          <Text size="xs" c="red" data-testid="sidebar-refresh-start-error">
            {refreshErrorMessage(startRefresh.error)}
          </Text>
        ) : null}
      </Stack>
    </Tooltip>
  );
}

export function SidebarFilters() {
  const { lookback, quarters, setLookback, toggleQuarter, reset } = useFilters();
  const location = useLocation();

  const lookbackData = LOOKBACK_OPTIONS.map((opt) => ({
    value: opt.value === null ? "all" : String(opt.value),
    label: opt.label,
  }));

  return (
    <Stack gap="md" p="md" data-testid="sidebar-filters">
      <Stack gap={2}>
        <Text size="xs" c="dimmed" tt="uppercase" fw={700}>
          Period
        </Text>
        <Select
          label="Lookback"
          data={lookbackData}
          value={lookback === null ? "all" : String(lookback)}
          onChange={(value) => {
            if (!value) return;
            if (value === "all") {
              setLookback(null);
              return;
            }
            const parsed = Number.parseInt(value, 10);
            if (Number.isFinite(parsed) && parsed > 0) {
              setLookback(parsed);
            }
          }}
          allowDeselect={false}
          data-testid="sidebar-lookback"
        />
        <Stack gap={6}>
          <Text size="sm" fw={500}>
            Quarters
          </Text>
          <Group gap="xs" data-testid="sidebar-quarters">
            {QUARTER_DATA.map(({ value, label }) => {
              const active = quarters.includes(value);
              return (
                <Button
                  key={value}
                  size="compact-sm"
                  variant={active ? "filled" : "light"}
                  color="navy"
                  onClick={() => toggleQuarter(value)}
                  aria-pressed={active}
                  data-testid={`sidebar-quarter-${value}`}
                >
                  {label}
                </Button>
              );
            })}
          </Group>
        </Stack>
        <Button
          variant="subtle"
          size="compact-sm"
          onClick={reset}
          data-testid="sidebar-reset"
        >
          Reset period
        </Button>
      </Stack>

      <Divider />

      <Stack gap={4} component="nav" aria-label="Dashboard pages">
        <Text size="xs" c="dimmed" tt="uppercase" fw={700}>
          Pages
        </Text>
        {NAV_ITEMS.map((item) => {
          const active = isActive(location.pathname, item.to);
          return (
            <Text
              key={item.to}
              component={Link}
              to={item.to}
              size="sm"
              fw={active ? 600 : 400}
              c={active ? "navy.7" : "dimmed"}
              py={4}
            >
              {item.label}
            </Text>
          );
        })}
      </Stack>

      <Divider />

      <Stack gap={4}>
        <Text size="xs" c="dimmed" tt="uppercase" fw={700}>
          Admin
        </Text>
        <SidebarRefreshControls />
      </Stack>
    </Stack>
  );
}
