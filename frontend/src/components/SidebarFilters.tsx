import { Button, Divider, Group, Progress, Select, Stack, Text, Tooltip } from "@mantine/core";
import { Link, useLocation } from "react-router-dom";

import { useCancelRefresh, useRefreshStatus, useStartRefresh } from "@/api/refresh";

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

function SidebarRefreshControls() {
  const refreshStatus = useRefreshStatus();
  const startRefresh = useStartRefresh();
  const cancelRefresh = useCancelRefresh();

  const status = refreshStatus.data?.status ?? "idle";
  const isRunning = status === "running";
  const progress = refreshStatus.data?.progress ?? 0;
  const currentStep = refreshStatus.data?.current_step ?? "";

  const primaryLabel = isRunning
    ? `Restart (${progress}%${currentStep ? ` — ${currentStep}` : ""})`
    : status === "succeeded"
      ? "Refresh data"
      : status === "failed" || status === "cancelled"
        ? "Retry refresh"
        : "Refresh data";

  return (
    <Tooltip
      label="Download and re-ingest House + Senate disclosure data (ingest-all)"
      multiline
      w={220}
    >
      <Stack gap="xs" data-testid="sidebar-admin">
        <Button
          color="navy"
          variant={isRunning ? "light" : "filled"}
          size="compact-sm"
          loading={startRefresh.isPending}
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
