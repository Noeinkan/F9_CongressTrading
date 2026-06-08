import {
  Anchor,
  Badge,
  Card,
  Group,
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

import {
  useTickerCumulativeExposure,
  useTickerMemberTimeline,
  useTickerPriceOverlay,
  useTickerProfile,
  useTickersList,
} from "@/api/tickers";
import { ChartCard } from "@/components/ChartCard";
import { CumulativeExposurePerMember } from "@/components/CumulativeExposurePerMember";
import { useFilters } from "@/components/FilterContext";
import { KpiTileSimple } from "@/components/KpiTileSimple";
import { PageState } from "@/components/PageState";
import { PillStrip } from "@/components/PillStrip";
import { PriceOverlayChart } from "@/components/PriceOverlayChart";
import { SectionIntro } from "@/components/SectionIntro";
import { TickerTimeline } from "@/components/TickerTimeline";
import { COPY } from "@/copy";
import { formatDate, msnMoneyQuoteUrl, yahooFinanceQuoteUrl } from "@/utils/format";

function quartersParam(quarters: string[]): string | undefined {
  if (quarters.length === 4) return undefined;
  return quarters.join(",");
}

export function Tickers() {
  const { lookback, quarters } = useFilters();
  const [searchParams, setSearchParams] = useSearchParams();
  const [manualTicker, setManualTicker] = useState(searchParams.get("ticker_override") ?? "");

  const periodParams = useMemo(
    () => ({ lookback, quarters: quartersParam(quarters) }),
    [lookback, quarters],
  );

  const listQuery = useTickersList({ ...periodParams, page: 1, page_size: 200 });
  const selectedTicker = searchParams.get("ticker") ?? listQuery.data?.rows[0]?.ticker ?? "";
  const tickerForView = manualTicker.trim().toUpperCase() || selectedTicker;

  const profile = useTickerProfile(tickerForView || null, periodParams);
  const priceOverlay = useTickerPriceOverlay(tickerForView || null, periodParams);
  const memberTimeline = useTickerMemberTimeline(tickerForView || null, periodParams);
  const cumulative = useTickerCumulativeExposure(tickerForView || null, periodParams);

  const tickerOptions = useMemo(
    () => (listQuery.data?.rows ?? []).map((r) => r.ticker),
    [listQuery.data?.rows],
  );

  const setSelectedTicker = (value: string | null) => {
    if (!value) return;
    const next = new URLSearchParams(searchParams);
    next.set("ticker", value);
    setSearchParams(next);
  };

  const timelineTypes = useMemo(() => {
    const labels = new Set(
      (memberTimeline.data?.rows ?? []).map(
        (r) => r.txn_type_label ?? r.transaction_type_label ?? "Unknown",
      ),
    );
    return [...labels];
  }, [memberTimeline.data?.rows]);

  const kpis = profile.data?.kpis;
  const issuer = profile.data?.issuer;

  return (
    <PageState
      isLoading={listQuery.isLoading}
      isError={listQuery.isError}
      ready={listQuery.data?.ready ?? false}
    >
      <Stack gap="md" data-testid="tickers-page">
        <SectionIntro
          kicker={COPY.tickers.kicker}
          title={COPY.tickers.title}
          copy={COPY.tickers.copy}
        />

        <Group grow align="flex-end">
          <Select
            label="Ticker"
            data={tickerOptions}
            value={selectedTicker || null}
            onChange={setSelectedTicker}
            searchable
            data-testid="tickers-select"
          />
          <TextInput
            label="Override symbol"
            placeholder="e.g. NVDA"
            value={manualTicker}
            onChange={(e) => setManualTicker(e.currentTarget.value.toUpperCase())}
            data-testid="tickers-override"
          />
        </Group>

        {!tickerForView ? (
          <Text c="dimmed">Select a ticker to view its profile.</Text>
        ) : (
          <Stack gap="md">
            {issuer?.issuer_name ? (
              <Card withBorder radius="md" padding="lg" data-testid="tickers-company-header">
                <Stack gap="xs">
                  <Group gap="xs">
                    <Title order={4}>{issuer.issuer_name}</Title>
                    <Badge variant="light">{tickerForView}</Badge>
                    {issuer.sector ? (
                      <Badge variant="light" color="teal">
                        {issuer.sector}
                      </Badge>
                    ) : null}
                    {issuer.industry ? (
                      <Badge variant="light" color="gray">
                        {issuer.industry}
                      </Badge>
                    ) : null}
                  </Group>
                </Stack>
              </Card>
            ) : (
              <Group gap="md">
                <Anchor href={yahooFinanceQuoteUrl(tickerForView)} target="_blank" rel="noreferrer">
                  Yahoo Finance
                </Anchor>
                <Anchor href={msnMoneyQuoteUrl(tickerForView)} target="_blank" rel="noreferrer">
                  MSN Money
                </Anchor>
              </Group>
            )}

            {kpis ? (
              <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing="md">
                <KpiTileSimple kpi={{ key: "trades", label: "Trades", value: kpis.trades }} />
                <KpiTileSimple kpi={{ key: "members", label: "Members", value: kpis.members }} />
                <KpiTileSimple
                  kpi={{
                    key: "buy_sell",
                    label: "Buy / sell",
                    value: `${kpis.buy} / ${kpis.sell}`,
                  }}
                />
                <KpiTileSimple
                  kpi={{
                    key: "range",
                    label: "Disclosed range",
                    value: profile.data?.disclosed_range ?? kpis.disclosed_range,
                  }}
                />
              </SimpleGrid>
            ) : null}

            <ChartCard title={COPY.tickers.whoTraded} testId="tickers-members-table">
              <Table.ScrollContainer minWidth={900}>
                <Table striped data-testid="tickers-who-traded">
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Member</Table.Th>
                      <Table.Th>Buys</Table.Th>
                      <Table.Th>Sells</Table.Th>
                      <Table.Th>Calls</Table.Th>
                      <Table.Th>Puts</Table.Th>
                      <Table.Th>Trades</Table.Th>
                      <Table.Th>Range</Table.Th>
                      <Table.Th>First</Table.Th>
                      <Table.Th>Last</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {(profile.data?.members ?? []).map((row) => (
                      <Table.Tr key={row.member}>
                        <Table.Td>
                          <Anchor
                            component={Link}
                            to={`/members?member=${encodeURIComponent(row.member)}`}
                            size="sm"
                          >
                            {row.member}
                          </Anchor>
                        </Table.Td>
                        <Table.Td>{row.buy}</Table.Td>
                        <Table.Td>{row.sell}</Table.Td>
                        <Table.Td>{row.call}</Table.Td>
                        <Table.Td>{row.put}</Table.Td>
                        <Table.Td>{row.trades}</Table.Td>
                        <Table.Td>{row.disclosed_range}</Table.Td>
                        <Table.Td>{formatDate(row.first_trade)}</Table.Td>
                        <Table.Td>{formatDate(row.last_trade)}</Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </Table.ScrollContainer>
            </ChartCard>

            <ChartCard title={COPY.tickers.priceOverlay} testId="tickers-price-overlay">
              {priceOverlay.data?.ready && priceOverlay.data.bars.length > 0 ? (
                <PriceOverlayChart
                  bars={priceOverlay.data.bars}
                  trades={priceOverlay.data.trades}
                />
              ) : (
                <Text c="dimmed" data-testid="tickers-no-polygon">
                  {COPY.tickers.noPolygon}
                </Text>
              )}
            </ChartCard>

            <ChartCard title={COPY.tickers.memberTimeline} testId="tickers-member-timeline">
              {timelineTypes.length ? (
                <PillStrip
                  testId="tickers-timeline-pills"
                  items={timelineTypes.map((label) => ({
                    label,
                    count: (memberTimeline.data?.rows ?? []).filter(
                      (r) => (r.txn_type_label ?? r.transaction_type_label) === label,
                    ).length,
                    color: "orange",
                  }))}
                />
              ) : null}
              <TickerTimeline
                rows={memberTimeline.data?.rows ?? []}
                yOrder={memberTimeline.data?.members}
                testId="tickers-timeline-chart"
              />
            </ChartCard>

            <ChartCard title={COPY.tickers.cumulativeExposure} testId="tickers-cumulative">
              <CumulativeExposurePerMember
                ticker={tickerForView}
                members={cumulative.data?.members ?? []}
                rows={cumulative.data?.rows ?? []}
                truncated={cumulative.data?.truncated}
              />
            </ChartCard>
          </Stack>
        )}
      </Stack>
    </PageState>
  );
}
