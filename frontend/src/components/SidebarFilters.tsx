import { Button, Divider, Select, Stack, Text } from "@mantine/core";

import {
  LOOKBACK_OPTIONS,
  QUARTER_VALUES,
  useFilters,
  type QuarterValue,
} from "./FilterContext";
import { NAV_ITEMS, isActive } from "./TopBar";
import { Link } from "react-router-dom";
import { Group } from "@mantine/core";
import { useLocation } from "react-router-dom";

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
    </Stack>
  );
}
