import {
  Anchor,
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
import { useMemo, useState, type CSSProperties } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { netTradeCsvUrl, useHomeSummary } from "@/api/home";
import { useTickerDrilldown } from "@/api/tickerDrilldown";
import { useTickerPriceOverlay } from "@/api/tickers";
import type { HomeTransactionRow } from "@/api/types";
import { ChartCard } from "@/components/ChartCard";
import { CumulativeExposurePerMember } from "@/components/CumulativeExposurePerMember";
import { DEFAULT_LOOKBACK, useFilters } from "@/components/FilterContext";
import { KpiTile } from "@/components/KpiTile";
import { MemberLink } from "@/components/MemberLink";
import { MembersLeaderboardTable } from "@/components/MembersLeaderboardTable";
import { MonthlyActivityChart } from "@/components/MonthlyActivityChart";
import { NetTradeChart } from "@/components/NetTradeChart";
import { PageState } from "@/components/PageState";
import { PillStrip } from "@/components/PillStrip";
import { PriceOverlayChart } from "@/components/PriceOverlayChart";
import { RankBars } from "@/components/RankBars";
import { TickerLink } from "@/components/TickerLink";
import { TickerTimeline } from "@/components/TickerTimeline";
import { COPY } from "@/copy";
import { useDemoLock } from "@/hooks/useDemoLock";
import { tickerHref } from "@/utils/entityLinks";
import { formatDate } from "@/utils/format";
import {
  classifyTransaction,
  directionColor,
  parseRangeHigh,
  rangeOpacity,
} from "@/utils/transactions";
import "./Home.css";

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
      scope="col"
      aria-sort={isActive ? (active.dir === "asc" ? "ascending" : "descending") : undefined}
    >
      <button
        type="button"
        className="home-sort"
        onClick={() =>
          onSort({ key: sortKey, dir: isActive && active.dir === "asc" ? "desc" : "asc" })
        }
        data-testid={`home-latest-sort-${sortKey}`}
      >
        {label} <span aria-hidden="true">{indicator}</span>
      </button>
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
  const csvLock = useDemoLock("csv_export");
  const flows = data?.net_trade_amounts ?? [];
  const [netBuy] = flows;
  const netSell = flows[flows.length - 1];
  const flowHighlights = [
    { label: "Largest net buy", row: netBuy && netBuy.net_amount > 0 ? netBuy : undefined },
    { label: "Largest net sell", row: netSell && netSell.net_amount < 0 ? netSell : undefined },
  ];
  const tickerPeriod = new URLSearchParams();
  if (lookback !== DEFAULT_LOOKBACK) {
    tickerPeriod.set("lookback", lookback === null ? "all" : String(lookback));
  }
  if (periodParams.quarters) tickerPeriod.set("quarters", periodParams.quarters);
  const tickerPeriodQuery = tickerPeriod.size ? `&${tickerPeriod}` : "";

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
  const priceOverlay = useTickerPriceOverlay(tickerForChart || null, periodParams);

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
        <Stack gap="md" className="home-dashboard" data-testid="home-page">
          <Card component="section" withBorder padding="md" className="home-overview" data-testid="home-hero">
            <div className="home-overview-layout">
              <Stack gap={6}>
                <Title order={1}>Congressional trading activity</Title>
                <Group gap="xs">
                  {data.hero.active_chambers
                    ? data.hero.active_chambers.split(", ").map((c) => (
                        <Badge key={c} variant="outline" color="navy">
                          {c}
                        </Badge>
                      ))
                    : null}
                  <Text size="sm" c="dimmed">
                    Trades from {formatDate(data.hero.coverage_from)} to {formatDate(data.hero.coverage_to)}
                  </Text>
                </Group>
              </Stack>
              <dl className="home-coverage">
                <div>
                  <dt>Latest filing</dt>
                  <dd>{formatDate(data.hero.latest_filing)}</dd>
                </div>
                <div>
                  <dt>Average confidence</dt>
                  <dd>{data.hero.avg_confidence_label}</dd>
                </div>
              </dl>
            </div>
            <details className="home-sources">
              <summary>Data sources</summary>
              <Text size="sm">Trades · {data.hero.transaction_source}</Text>
              <Text size="sm">Reviews · {data.hero.review_source}</Text>
            </details>
          </Card>

          <SimpleGrid cols={{ base: 2, md: 3, lg: 5 }} spacing="sm" className="home-kpis">
            {data.kpis.map((kpi) => (
              <KpiTile key={kpi.key} kpi={kpi} compact />
            ))}
          </SimpleGrid>

          <div className="home-workspace">
            <ChartCard
              collapsible
              id="home-latest-detail"
              title="Latest activity"
              caption={`${visibleLatestRows.length} of ${data.latest_transactions.length} recent trades. Select a member or ticker to investigate.`}
              headerRight={
                <Group gap="xs" data-testid="home-latest-size">
                  <Text size="xs" c="dimmed">
                    Rows
                  </Text>
                  <SegmentedControl
                    aria-label="Rows to show"
                    value={latestSize}
                    onChange={setLatestSize}
                    data={LATEST_SIZE_OPTIONS}
                    size="xs"
                  />
                </Group>
              }
            >
              <Text size="xs" c="dimmed" className="home-scroll-hint">
                Scroll across for trade dates and disclosed amounts.
              </Text>
              <div className="home-trade-scroll" tabIndex={0} role="region" aria-label="Recent transactions">
                <Table stickyHeader striped highlightOnHover className="home-trade-table" data-testid="home-latest-table">
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
                        label="Disclosed range"
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
                      const emphasis = rangeOpacity(row.amount_range_raw);
                      return (
                        <Table.Tr
                          key={`${row.member}-${row.transaction_date}-${i}`}
                          data-testid="home-latest-row"
                        >
                          <Table.Td>
                            <MemberLink name={row.member} />
                          </Table.Td>
                          <Table.Td>
                            {row.ticker ? (
                              <TickerLink
                                ticker={row.ticker}
                                fw={500}
                                data-testid="home-latest-ticker"
                              />
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
                              className="home-direction"
                              style={{ "--home-trade-emphasis": `${Math.round(emphasis * 18)}%` } as CSSProperties}
                              data-testid="home-latest-type"
                              data-direction={direction}
                            >
                              {row.transaction_type_label || "—"}
                            </Badge>
                          </Table.Td>
                          <Table.Td>{formatDate(row.transaction_date)}</Table.Td>
                          <Table.Td>
                            <Text
                              size="sm"
                              className="home-trade-amount"
                              data-testid="home-latest-range"
                              data-direction={direction}
                            >
                              {row.amount_range_raw || "—"}
                            </Text>
                          </Table.Td>
                        </Table.Tr>
                      );
                    })}
                    {visibleLatestRows.length === 0 ? (
                      <Table.Tr><Table.Td colSpan={5}>No recent trades in this period.</Table.Td></Table.Tr>
                    ) : null}
                  </Table.Tbody>
                </Table>
              </div>
            </ChartCard>

            <Stack component="aside" gap="md" aria-label="Research shortcuts">
              <Card withBorder padding="md" className="home-flow">
                <Stack gap="sm">
                  <div>
                    <Title order={2}>Net flow leaders</Title>
                    <Text size="sm" c="dimmed">Estimated net trade amounts in this period.</Text>
                  </div>
                  {flowHighlights.map(({ label, row }) => row ? (
                    <Anchor
                      key={label}
                      component={Link}
                      to={`${tickerHref(row.ticker)}${tickerPeriodQuery}`}
                      className="home-flow-link"
                    >
                      <Text component="span" size="xs" c="dimmed">{label}</Text>
                      <span className="home-flow-value">
                        <strong>{row.ticker}</strong>
                        <span data-direction={row.net_amount > 0 ? "buy" : "sell"}>{row.net_label}</span>
                      </span>
                    </Anchor>
                  ) : null)}
                  {flows.length === 0 ? <Text size="sm">No directional amounts for this period.</Text> : null}
                  <Text size="sm" c="dimmed">Open a ticker to see price history and return since trade when available.</Text>
                  <Anchor href="#home-flow-detail" size="sm" fw={600}>See net trade breakdown ↓</Anchor>
                </Stack>
              </Card>
              <Card component="nav" aria-label="Explore this page" withBorder padding="md">
                <Title order={2} className="home-explore-title">Explore this page</Title>
                <Group gap="sm" mt="xs">
                  <Anchor href="#home-monthly-detail" size="sm">Monthly activity</Anchor>
                  <Anchor href="#home-leaderboard-detail" size="sm">Members leaderboard</Anchor>
                  <Anchor href="#home-ticker-detail" size="sm">Ticker drill-down</Anchor>
                </Group>
              </Card>
            </Stack>
          </div>

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
            collapsible
            id="home-flow-detail"
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
                  onClick={(event) => {
                    if (csvLock.locked) {
                      event.preventDefault();
                      csvLock.open();
                    }
                  }}
                  data-testid="home-net-download"
                >
                  CSV
                </Button>
                {csvLock.locked ? (
                  <Text size="xs" c="dimmed" data-testid="home-net-download-lock-hint">
                    Available with full access
                  </Text>
                ) : null}
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
                      <Table.Td>
                        <TickerLink ticker={row.ticker} />
                      </Table.Td>
                      <Table.Td>{row.direction}</Table.Td>
                      <Table.Td>{row.net_label}</Table.Td>
                      <Table.Td>{row.trades}</Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            )}
          </ChartCard>

          <ChartCard collapsible id="home-monthly-detail" title="Monthly activity" caption={COPY.home.monthlyActivity}>
            <MonthlyActivityChart rows={data.monthly_activity} />
          </ChartCard>

          <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
            <ChartCard collapsible title="Top members">
              <RankBars
                testId="home-top-members"
                color="#20344a"
                linkKind="member"
                rows={data.top_members.map((r) => ({
                  label: r.member ?? "",
                  value: r.transactions,
                }))}
              />
            </ChartCard>
            <ChartCard collapsible title="Top tickers">
              <RankBars
                testId="home-top-tickers"
                color="#c6922b"
                linkKind="ticker"
                rows={data.top_tickers.map((r) => ({
                  label: r.ticker ?? "",
                  value: r.transactions,
                }))}
              />
            </ChartCard>
          </SimpleGrid>

          <ChartCard
            collapsible
            id="home-leaderboard-detail"
            title="Members leaderboard"
            caption="Full per-filer ranking for the active period slice. Click a name to open the profile on the Members page."
            testId="home-leaderboard"
          >
            <MembersLeaderboardTable
              rows={data.members_leaderboard}
              testId="home-leaderboard-table"
            />
          </ChartCard>

          <ChartCard
            collapsible
            defaultCollapsed
            id="home-ticker-detail"
            title="Ticker drill-down"
            caption="Quick peek here, or open the full Tickers page for price overlay and exposure charts."
            testId="home-drilldown"
            headerRight={
              <Anchor component={Link} to="/tickers" size="sm" data-testid="home-drilldown-tickers-link">
                Open Tickers page
              </Anchor>
            }
          >
            {data.tickers_available.length === 0 ? (
              <Text c="dimmed">No resolved tickers in the current slice.</Text>
            ) : (
              <Stack gap="md">
                <Group align="flex-end" wrap="wrap">
                  <Select
                    label="Ticker"
                    data={data.tickers_available}
                    value={selectedTicker || null}
                    onChange={setSelectedTicker}
                    searchable
                    style={{ flex: 1, minWidth: 160 }}
                    data-testid="home-ticker-select"
                  />
                  <TextInput
                    label="Or type a symbol"
                    placeholder="e.g. MSFT"
                    value={manualTicker}
                    onChange={(e) => setManualTicker(e.currentTarget.value.toUpperCase())}
                    style={{ flex: 1, minWidth: 160 }}
                    data-testid="home-ticker-override"
                  />
                  {tickerForChart ? (
                    <Button
                      component={Link}
                      to={tickerHref(tickerForChart, manualTicker)}
                      variant="light"
                      data-testid="home-open-tickers"
                    >
                      Open on Tickers
                    </Button>
                  ) : null}
                </Group>
                {tickerForChart ? (
                  <Stack gap="lg">
                    <div>
                      <Title order={5} mb="xs">
                        Price & trade overlay
                      </Title>
                      {priceOverlay.data?.ready && priceOverlay.data.bars.length > 0 ? (
                        <PriceOverlayChart
                          bars={priceOverlay.data.bars}
                          trades={priceOverlay.data.trades}
                          testId="home-price-overlay"
                        />
                      ) : (
                        <Text c="dimmed" data-testid="home-no-polygon">
                          {COPY.tickers.noPolygon}
                        </Text>
                      )}
                    </div>
                    <div>
                      <Title order={5} mb="xs">
                        Member timeline
                      </Title>
                      <Text c="dimmed" size="sm" mb="xs">
                        Color is buy/sell; bubble size scales with disclosed high amount.
                      </Text>
                      <TickerTimeline rows={drilldown.data?.ticker_timeline ?? []} />
                    </div>
                    <div>
                      <Title order={5} mb="xs">
                        Cumulative exposure
                      </Title>
                      <CumulativeExposurePerMember
                        ticker={tickerForChart}
                        members={drilldown.data?.ticker_cumulative?.members ?? []}
                        rows={drilldown.data?.ticker_cumulative?.rows ?? []}
                        truncated={drilldown.data?.ticker_cumulative?.truncated}
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
