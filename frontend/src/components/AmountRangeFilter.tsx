import { Accordion, Badge, Button, Group, Stack, Text, UnstyledButton } from "@mantine/core";

import {
  DISCLOSED_RANGE_BUCKETS,
  classifyAmountRange,
  type DisclosedRangeBucket,
} from "@/utils/transactions";

export type AmountRangeFilterValue = string | null;

type AmountRange = {
  amount_low?: number | null;
  amount_high?: number | null;
  amount_range_raw?: string | null;
};

type AmountRangeFilterProps = {
  /**
   * Rows used to compute per-bucket counts. The filter does NOT own the rows
   * — the parent renders the table from `rows` (optionally filtered by the
   * current `value`). This keeps the component reusable across the
   * ticker/member trade-history tables.
   */
  rows: AmountRange[];
  /** Currently selected bucket key, or `null` for "All". */
  value: AmountRangeFilterValue;
  onChange: (value: AmountRangeFilterValue) => void;
  testId?: string;
};

function countInBucket(rows: AmountRange[], bucket: DisclosedRangeBucket): number {
  let count = 0;
  for (const row of rows) {
    if (classifyAmountRange(row) === bucket.key) count += 1;
  }
  return count;
}

function CountBadge({ count, selected }: { count: number; selected: boolean }) {
  return (
    <Badge variant={selected ? "filled" : "light"} color={selected ? "blue" : "gray"} size="sm">
      {count.toLocaleString()}
    </Badge>
  );
}

/**
 * Accordion-hosted bucket selector that mirrors the canonical House/Senate
 * PTR disclosure bands. The outer accordion collapses the band list so it
 * doesn't dominate the page; clicking a band filters the parent's table and
 * highlights that row. Use the "Clear filter" button to reset.
 */
export function AmountRangeFilter({
  rows,
  value,
  onChange,
  testId = "amount-range-filter",
}: AmountRangeFilterProps) {
  const total = rows.length;
  const knownCount = rows.reduce(
    (acc, row) => (classifyAmountRange(row) ? acc + 1 : acc),
    0,
  );
  const unknownCount = total - knownCount;
  const activeLabel = value
    ? DISCLOSED_RANGE_BUCKETS.find((b) => b.key === value)?.label
    : null;

  return (
    <Accordion
      variant="separated"
      radius="md"
      data-testid={testId}
      styles={{
        item: { backgroundColor: "var(--mantine-color-body)" },
      }}
    >
      <Accordion.Item value="amount-ranges">
        <Accordion.Control>
          <Text fw={600} size="sm">
            Filter by disclosed amount range
          </Text>
        </Accordion.Control>
        <Accordion.Panel>
          <Stack gap={4} data-testid={`${testId}-items`}>
            <Group justify="space-between" wrap="nowrap" gap="sm" px="sm">
              <Text size="xs" c="dimmed" tt="uppercase" fw={700}>
                Range
              </Text>
              <Group gap="xs" wrap="nowrap">
                {value ? (
                  <Button
                    size="compact-xs"
                    variant="subtle"
                    onClick={() => onChange(null)}
                    data-testid={`${testId}-reset`}
                  >
                    Clear filter
                  </Button>
                ) : null}
                <Badge variant="light" color="blue" size="sm">
                  {activeLabel ?? `All ${total.toLocaleString()}`}
                </Badge>
              </Group>
            </Group>
            <UnstyledButton
              onClick={() => onChange(null)}
              data-testid={`${testId}-item-all`}
              style={{
                padding: "8px 12px",
                borderRadius: 6,
                backgroundColor: value == null ? "var(--mantine-color-blue-light)" : undefined,
              }}
            >
              <Group justify="space-between" wrap="nowrap" gap="sm">
                <Text size="sm" fw={value == null ? 600 : 400}>
                  All ranges
                </Text>
                <CountBadge count={total} selected={value == null} />
              </Group>
            </UnstyledButton>
            {DISCLOSED_RANGE_BUCKETS.map((bucket) => {
              const count = countInBucket(rows, bucket);
              const selected = value === bucket.key;
              return (
                <UnstyledButton
                  key={bucket.key}
                  onClick={() => onChange(bucket.key)}
                  data-testid={`${testId}-item-${bucket.key}`}
                  style={{
                    padding: "8px 12px",
                    borderRadius: 6,
                    backgroundColor: selected
                      ? "var(--mantine-color-blue-light)"
                      : undefined,
                    opacity: count === 0 ? 0.55 : 1,
                  }}
                  aria-pressed={selected}
                >
                  <Group justify="space-between" wrap="nowrap" gap="sm">
                    <Text size="sm" fw={selected ? 600 : 400}>
                      {bucket.label}
                    </Text>
                    <CountBadge count={count} selected={selected} />
                  </Group>
                </UnstyledButton>
              );
            })}
            {unknownCount > 0 ? (
              <Group
                justify="space-between"
                wrap="nowrap"
                gap="sm"
                px="sm"
                py="xs"
                data-testid={`${testId}-item-unknown`}
              >
                <Text size="sm" c="dimmed">
                  Unknown / unparsed
                </Text>
                <CountBadge count={unknownCount} selected={false} />
              </Group>
            ) : null}
          </Stack>
        </Accordion.Panel>
      </Accordion.Item>
    </Accordion>
  );
}