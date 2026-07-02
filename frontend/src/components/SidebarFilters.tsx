import { Button, Divider, Group, Progress, Select, Stack, Text, Tooltip } from "@mantine/core";
import { Link, useLocation } from "react-router-dom";

import { ApiError } from "@/api/client";
import { useCancelRefresh, useRefreshStatus, useStartRefresh } from "@/api/refresh";
import { RefreshLogPanel } from "@/components/RefreshLogPanel";

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

function SidebarRefreshControls() {
  const refreshStatus = useRefreshStatus();
  const startRefresh = useStartRefresh();
  const cancelRefresh = useCancelRefresh();

  const status = refreshStatus.data?.status ?? "idle";
  const isRunning = status === "running" || startRefresh.isPending;
  const progress = refreshStatus.data?.progress ?? 0;
  const currentStep = refreshStatus.data?.current_step ?? "";
  const failedMessage =
    typeof refreshStatus.data?.result?.error === "string"
      ? refreshStatus.data.result.error
      : null;
  const logLines =
    refreshStatus.data?.log_lines ??
    refreshStatus.data?.log_tail ??
    [];
  const showLogPanel =
    isRunning || (status !== "idle" && (logLines.length > 0 || Boolean(refreshStatus.data?.started_at)));

  // useStartRefresh already drops the cache in onMutate, so no separate
  // status effect is needed here.

  const primaryLabel = isRunning
    ? `Restart (${progress}%${currentStep ? ` — ${currentStep}` : ""})`
    : status === "failed" || status === "cancelled"
      ? "Retry refresh"
      : "Refresh data";

  const resultSummary = (() => {
    const result = refreshStatus.data?.result;
    if (!result || typeof result !== "object") return null;
    const rowsPtr = typeof result.house_fd_rows_ptr === "number" ? result.house_fd_rows_ptr : null;
    const rowsTotal = typeof result.house_fd_rows_total === "number" ? result.house_fd_rows_total : null;
    const senate = (result as { senate?: { pdfs?: number; reason?: string } }).senate;
    if (rowsPtr == null && rowsTotal == null && !senate) return null;
    return { rowsPtr, rowsTotal, senate };
  })();

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
            {currentStep ? (
              <Text size="xs" c="dimmed">
                {currentStep}
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
          <RefreshLogPanel
            lines={logLines}
            startedAt={refreshStatus.data?.started_at ?? null}
            isLive={isRunning}
          />
        ) : null}
        {!isRunning && status === "succeeded" && resultSummary ? (
          <Stack gap={2} data-testid="sidebar-refresh-summary">
            {resultSummary.rowsPtr != null ? (
              <Text size="xs" c="teal">
                {resultSummary.rowsPtr} PTR rows seen across FD metadata
                {resultSummary.rowsTotal != null ? ` (${resultSummary.rowsTotal} total)` : ""}
              </Text>
            ) : null}
          </Stack>
        ) : null}
        {!isRunning && status === "succeeded" ? (
          <Text size="xs" c="teal" data-testid="sidebar-refresh-success">
            Refresh completed
          </Text>
        ) : null}
        {!isRunning && status === "failed" ? (
          <Text size="xs" c="red" data-testid="sidebar-refresh-error">
            {failedMessage ?? "Refresh failed — check server logs"}
          </Text>
        ) : null}
        {!isRunning && status === "cancelled" ? (
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
