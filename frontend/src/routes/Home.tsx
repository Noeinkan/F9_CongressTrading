import {
  Badge,
  Button,
  Card,
  Group,
  SegmentedControl,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { netTradeCsvUrl, useHomeSummary } from "@/api/home";
import { useTickerDrilldown } from "@/api/tickerDrilldown";
import type { HomeTransactionRow } from "@/api/types";
import { ChartCard } from "@/components/ChartCard";
import { CumulativeExposure } from "@/components/CumulativeExposure";
import { useFilters } from "@/components/FilterContext";
import { KpiTile } from "@/components/KpiTile";
import { MonthlyActivityChart } from "@/components/MonthlyActivityChart";
import { NetTradeChart } from "@/components/NetTradeChart";
import { PageState } from "@/components/PageState";
import { PillStrip } from "@/components/PillStrip";
import { RankBars } from "@/components/RankBars";
import { SectionIntro } from "@/components/SectionIntro";
import { Ticker3D } from "@/components/Ticker3D";
import { TickerTimeline } from "@/components/TickerTimeline";
import { formatDate, formatDisclosedRange } from "@/utils/format";
import {
  classifyTransaction,
  directionColor,
  parseRangeHigh,
  rangeOpacity,
} from "@/utils/transactions";

type LatestSortKey =
  | "member"
  | "ticker"
  | "transaction_type_label"
  | "transaction_date"
  | "amount_range_raw";
type SortDir = "asc" | "desc";

const LATEST_SIZE_OPTIONS = ["25", "50", "75", "100"];

function compareLatestRows(
  a: HomeTransactionRow,
  b: HomeTransactionRow,
  key: LatestSortKey,
  dir: SortDir,
): number {
  const sign = dir === "asc" ? 1 : -1;
  if (key === "transaction_date") {
    const av = a.transaction_date ?? "";
    const bv = b.transaction_date ?? "";
    return av.localeCompare(bv) * sign;
  }
  if (key === "amount_range_raw") {
    return (parseRangeHigh(a.amount_range_raw) - parseRangeHigh(b.amount_range_raw)) * sign;
  }
  const av = String(a[key] ?? "").toLowerCase();
  const bv = String(b[key] ?? "").toLowerCase();
  if (av < bv) return -1 * sign;
  if (av > bv) return 1 * sign;
  return 0;
}

type SortableThProps = {
  label: string;
  sortKey: LatestSortKey;
  active: { key: LatestSortKey; dir: SortDir };
  onSort: (next: { key: LatestSortKey; dir: SortDir }) => void;
};

function SortableTh({ label, sortKey, active, onSort }: SortableThProps) {
  const isActive = active.key === sortKey;
  const indicator = !isActive ? "↕" : active.dir === "asc" ? "↑" : "↓";
  return (
    <Table.Th
      role="button"
      tabIndex={0}
      aria-sort={isActive ? (active.dir === "asc" ? "ascending" : "descending") : "none"}
      onClick={() =>
        onSort({ key: sortKey, dir: isActive && active.dir === "asc" ? "desc" : "asc" })
      }
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSort({ key: sortKey, dir: isActive && active.dir === "asc" ? "desc" : "asc" });
        }
      }}
      style={{ cursor: "pointer", userSelect: "none" }}
      data-testid={`home-latest-sort-${sortKey}`}
    >
      <span>
        {label} <span style={{ opacity: 0.5, fontSize: "0.85em" }}>{indicator}</span>
      </span>
    </Table.Th>
  );
}

function quartersParam(quarters: string[]): string | undefined {
  if (quarters.length === 4) return undefined;
  return quarters.join(",");
}

export function Home() {
  const { lookback, quarters } = useFilters();
  const [searchParams, setSearchParams] = useSearchParams();
  const [manualTicker, setManualTicker] = useState(searchParams.get("ticker_override") ?? "");
  const [latestSize, setLatestSize] = useState<string>(LATEST_SIZE_OPTIONS[0] ?? "25");
  const [latestSort, setLatestSort] = useState<{ key: LatestSortKey; dir: SortDir }>({
    key: "transaction_date",
    dir: "desc",
  });

  const periodParams = useMemo(
    () => ({ lookback, quarters: quartersParam(quarters) }),
    [lookback, quarters],
  );

  const { data, isLoading, isError } = useHomeSummary(periodParams);

  const visibleLatestRows = useMemo(() => {
    const rows = data?.latest_transactions ?? [];
    const size = Number(latestSize) || 25;
    const sorted = [...rows].sort((a, b) =>
      compareLatestRows(a, b, latestSort.key, latestSort.dir),
    );
    return sorted.slice(0, size);
  }, [data?.latest_transactions, latestSize, latestSort]);

  const netView = (searchParams.get("net_view") ?? "chart") as "chart" | "table";
  const selectedTicker = searchParams.get("ticker") ?? data?.tickers_available[0] ?? "";
  const tickerForChart = manualTicker.trim().toUpperCase() || selectedTicker;

  const drilldown = useTickerDrilldown(tickerForChart || null, periodParams);

  const setNetView = (value: string) => {
    const next = new URLSearchParams(searchParams);
    next.set("net_view", value);
    setSearchParams(next);
  };

  const setSelectedTicker = (value: string | null) => {
    if (!value) return;
    const next = new URLSearchParams(searchParams);
    next.set("ticker", value);
    setSearchParams(next);
  };

  return (
    <PageState isLoading={isLoading} isError={isError} ready={data?.ready ?? false}>
      {data ? (
        <Stack gap="md" data-testid="home-page">
          <SectionIntro
            kicker="Overview"
            title="Where activity is clustering"
            copy="KPIs, sparklines, and rollups for the active period slice from /api/home/summary."
          />

          <Card withBorder radius="md" padding="lg" data-testid="home-hero">
            <SimpleGrid cols={{ base: 1, md: 2 }} spacing="lg">
              <Stack gap="xs">
                <Text size="xs" c="dimmed" tt="uppercase" fw={700}>
                  Congress Trading
                </Text>
                <Title order={2}>Activity in the active slice</Title>
                <Text c="dimmed" size="sm">
                  {data.hero.disclosed_range} disclosed across {data.hero.total_transactions.toLocaleString()}{" "}
                  transactions from {data.hero.total_members} members.
                </Text>
                <Group gap="xs">
                  {data.hero.active_chambers
                    ? data.hero.active_chambers.split(", ").map((c) => (
                        <Badge key={c} variant="light" color="teal">
                          {c}
                        </Badge>
                      ))
                    : null}
                  <Badge variant="light" color="navy">
                    {data.hero.tracked_tickers} tickers
                  </Badge>
                  <Badge variant="light" color="orange">
                    {data.hero.open_reviews} open reviews
                  </Badge>
                </Group>
              </Stack>
              <Stack gap={4}>
                <Text size="sm">
                  <Text span fw={600}>
                    Coverage:
                  </Text>{" "}
                  {formatDate(data.hero.coverage_from)} – {formatDate(data.hero.coverage_to)}
                </Text>
                <Text size="sm">
                  <Text span fw={600}>
                    Avg confidence:
                  </Text>{" "}
                  {data.hero.avg_confidence_label}
                </Text>
                <Text size="xs" c="dimmed">
                  Sources: {data.hero.transaction_source} · {data.hero.review_source}
                </Text>
              </Stack>
            </SimpleGrid>
          </Card>

          <SimpleGrid cols={{ base: 1, sm: 2, lg: 5 }} spacing="md">
            {data.kpis.map((kpi) => (
              <KpiTile key={kpi.key} kpi={kpi} />
            ))}
          </SimpleGrid>

          <ChartCard
            title="Latest activity"
            caption="Most recent disclosures in the slice (preview). Click a ticker to open its profile."
            headerRight={
              <Group gap="xs" data-testid="home-latest-size">
                <Text size="xs" c="dimmed">
                  Rows
                </Text>
                <SegmentedControl
                  value={latestSize}
                  onChange={setLatestSize}
                  data={LATEST_SIZE_OPTIONS}
                  size="xs"
                />
              </Group>
            }
          >
            <Table.ScrollContainer minWidth={700}>
              <Table striped highlightOnHover data-testid="home-latest-table">
                <Table.Thead>
                  <Table.Tr>
                    <SortableTh
                      label="Member"
                      sortKey="member"
                      active={latestSort}
                      onSort={setLatestSort}
                    />
                    <SortableTh
                      label="Ticker"
                      sortKey="ticker"
                      active={latestSort}
                      onSort={setLatestSort}
                    />
                    <SortableTh
                      label="Type"
                      sortKey="transaction_type_label"
                      active={latestSort}
                      onSort={setLatestSort}
                    />
                    <SortableTh
                      label="Traded"
                      sortKey="transaction_date"
                      active={latestSort}
                      onSort={setLatestSort}
                    />
                    <SortableTh
                      label="Range"
                      sortKey="amount_range_raw"
                      active={latestSort}
                      onSort={setLatestSort}
                    />
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {visibleLatestRows.map((row, i) => {
                    const direction = classifyTransaction(row.transaction_type_label);
                    const color = directionColor(direction);
                    const opacity = rangeOpacity(row.amount_range_raw);
                    const badgeStyle = { opacity } as const;
                    return (
                      <Table.Tr
                        key={`${row.member}-${row.transaction_date}-${i}`}
                        data-testid="home-latest-row"
                      >
                        <Table.Td>
                          <Text
                            component={Link}
                            to={`/members?member=${encodeURIComponent(row.member)}`}
                            size="sm"
                          >
                            {row.member}
                          </Text>
                        </Table.Td>
                        <Table.Td>
                          {row.ticker ? (
                            <Text
                              component={Link}
                              to={`/tickers?ticker=${encodeURIComponent(row.ticker)}`}
                              size="sm"
                              fw={500}
                              data-testid="home-latest-ticker"
                            >
                              {row.ticker}
                            </Text>
                          ) : (
                            <Text size="sm" fw={500}>
                              —
                            </Text>
                          )}
                          {row.issuer_name ? (
                            <Text size="xs" c="dimmed" lineClamp={1}>
                              {row.issuer_name}
                            </Text>
                          ) : null}
                        </Table.Td>
                        <Table.Td>
                          <Badge
                            variant="light"
                            color={color}
                            style={badgeStyle}
                            data-testid="home-latest-type"
                            data-direction={direction}
                          >
                            {row.transaction_type_label || "—"}
                          </Badge>
                        </Table.Td>
                        <Table.Td>{formatDate(row.transaction_date)}</Table.Td>
                        <Table.Td>
                          <Text size="sm" style={{ opacity }}>
                            {row.amount_range_raw}
                          </Text>
                        </Table.Td>
                      </Table.Tr>
                    );
                  })}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
          </ChartCard>

          <Stack gap="xs">
            <PillStrip
              testId="home-chamber-pills"
              items={data.breakdown.by_chamber.map((r) => ({
                label: r.chamber,
                count: r.transactions,
                color: "teal",
              }))}
            />
            <PillStrip
              testId="home-type-pills"
              items={data.breakdown.by_type.map((r) => ({
                label: r.transaction_type_label,
                count: r.transactions,
                color: "orange",
              }))}
            />
          </Stack>

          <ChartCard
            title="Net trade amount"
            caption="Net signed dollar flow per ticker — green is net buying, red is net selling."
            testId="home-net-trade"
            headerRight={
              <Group gap="xs">
                <SegmentedControl
                  value={netView}
                  onChange={setNetView}
                  data={[
                    { label: "Chart", value: "chart" },
                    { label: "Table", value: "table" },
                  ]}
                  size="xs"
                  data-testid="home-net-view"
                />
                <Button
                  component="a"
                  href={netTradeCsvUrl(periodParams)}
                  download
                  size="compact-sm"
                  variant="light"
                  disabled={netView !== "table"}
                  data-testid="home-net-download"
                >
                  CSV
                </Button>
              </Group>
            }
          >
            {data.net_trade_amounts.length === 0 ? (
              <Text c="dimmed">No resolved tickers with directional amounts in the current filter.</Text>
            ) : netView === "chart" ? (
              <NetTradeChart rows={data.net_trade_amounts} />
            ) : (
              <Table data-testid="home-net-table">
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Ticker</Table.Th>
                    <Table.Th>Direction</Table.Th>
                    <Table.Th>Net</Table.Th>
                    <Table.Th>Trades</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {data.net_trade_amounts.map((row) => (
                    <Table.Tr key={row.ticker}>
                      <Table.Td>{row.ticker}</Table.Td>
                      <Table.Td>{row.direction}</Table.Td>
                      <Table.Td>{row.net_label}</Table.Td>
                      <Table.Td>{row.trades}</Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            )}
          </ChartCard>

          <ChartCard title="Monthly activity">
            <MonthlyActivityChart rows={data.monthly_activity} />
          </ChartCard>

          <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
            <ChartCard title="Top members">
              <RankBars
                testId="home-top-members"
                color="#20344a"
                rows={data.top_members.map((r) => ({
                  label: r.member ?? "",
                  value: r.transactions,
                }))}
              />
            </ChartCard>
            <ChartCard title="Top tickers">
              <RankBars
                testId="home-top-tickers"
                color="#c6922b"
                rows={data.top_tickers.map((r) => ({
                  label: r.ticker ?? "",
                  value: r.transactions,
                }))}
              />
            </ChartCard>
          </SimpleGrid>

          <ChartCard
            title="Members leaderboard"
            caption="Full per-filer ranking for the active period slice. Click a row to open the profile on the Members page."
            testId="home-leaderboard"
          >
            {data.members_leaderboard.length === 0 ? (
              <Text c="dimmed">No members in the current slice.</Text>
            ) : (
              <Table.ScrollContainer minWidth={800}>
                <Table striped highlightOnHover data-testid="home-leaderboard-table">
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Member</Table.Th>
                      <Table.Th>Trades</Table.Th>
                      <Table.Th>Tickers</Table.Th>
                      <Table.Th>Disclosed range</Table.Th>
                      <Table.Th>Chamber</Table.Th>
                      <Table.Th>Party</Table.Th>
                      <Table.Th>State</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {data.members_leaderboard.map((row) => (
                      <Table.Tr
                        key={row.member}
                        style={{ cursor: "pointer" }}
                        data-testid="home-leaderboard-row"
                      >
                        <Table.Td>
                          <Text
                            component={Link}
                            to={`/members?member=${encodeURIComponent(row.member)}`}
                            size="sm"
                            fw={500}
                          >
                            {row.member}
                          </Text>
                        </Table.Td>
                        <Table.Td>{row.trades}</Table.Td>
                        <Table.Td>{row.tickers}</Table.Td>
                        <Table.Td>
                          {row.disclosed_range ??
                            formatDisclosedRange(row.amount_low, row.amount_high)}
                        </Table.Td>
                        <Table.Td>{row.chamber}</Table.Td>
                        <Table.Td>{row.party}</Table.Td>
                        <Table.Td>{row.state}</Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </Table.ScrollContainer>
            )}
          </ChartCard>

          <ChartCard title="Ticker drill-down" testId="home-drilldown">
            {data.tickers_available.length === 0 ? (
              <Text c="dimmed">No resolved tickers in the current slice.</Text>
            ) : (
              <Stack gap="md">
                <Group grow>
                  <Select
                    label="Ticker"
                    data={data.tickers_available}
                    value={selectedTicker || null}
                    onChange={setSelectedTicker}
                    searchable
                    data-testid="home-ticker-select"
                  />
                  <TextInput
                    label="Override symbol"
                    placeholder="e.g. MSFT"
                    value={manualTicker}
                    onChange={(e) => setManualTicker(e.currentTarget.value.toUpperCase())}
                    data-testid="home-ticker-override"
                  />
                </Group>
                {tickerForChart ? (
                  <Stack gap="lg">
                    <div>
                      <Title order={5} mb="xs">
                        Member timeline
                      </Title>
                      <TickerTimeline rows={drilldown.data?.ticker_timeline ?? []} />
                    </div>
                    <div>
                      <Title order={5} mb="xs">
                        3D scatter
                      </Title>
                      <Ticker3D rows={drilldown.data?.ticker_3d ?? []} />
                    </div>
                    <div>
                      <Title order={5} mb="xs">
                        Cumulative exposure
                      </Title>
                      <CumulativeExposure
                        ticker={tickerForChart}
                        rows={drilldown.data?.ticker_cumulative ?? []}
                      />
                    </div>
                  </Stack>
                ) : null}
              </Stack>
            )}
          </ChartCard>
        </Stack>
      ) : null}
    </PageState>
  );
}
