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

function quartersParam(quarters: string[]): string | undefined {
  if (quarters.length === 4) return undefined;
  return quarters.join(",");
}

export function Home() {
  const { lookback, quarters } = useFilters();
  const [searchParams, setSearchParams] = useSearchParams();
  const [manualTicker, setManualTicker] = useState(searchParams.get("ticker_override") ?? "");

  const periodParams = useMemo(
    () => ({ lookback, quarters: quartersParam(quarters) }),
    [lookback, quarters],
  );

  const { data, isLoading, isError } = useHomeSummary(periodParams);

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

          <ChartCard title="Latest activity" caption="Most recent disclosures in the slice (preview).">
            <Table.ScrollContainer minWidth={700}>
              <Table striped data-testid="home-latest-table">
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Member</Table.Th>
                    <Table.Th>Ticker</Table.Th>
                    <Table.Th>Type</Table.Th>
                    <Table.Th>Traded</Table.Th>
                    <Table.Th>Range</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {data.latest_transactions.slice(0, 10).map((row, i) => (
                    <Table.Tr key={`${row.member}-${row.transaction_date}-${i}`}>
                      <Table.Td>
                        <Text
                          component={Link}
                          to={`/members?member=${encodeURIComponent(row.member)}`}
                          size="sm"
                        >
                          {row.member}
                        </Text>
                      </Table.Td>
                      <Table.Td>{row.ticker || "—"}</Table.Td>
                      <Table.Td>{row.transaction_type_label}</Table.Td>
                      <Table.Td>{formatDate(row.transaction_date)}</Table.Td>
                      <Table.Td>{row.amount_range_raw}</Table.Td>
                    </Table.Tr>
                  ))}
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
