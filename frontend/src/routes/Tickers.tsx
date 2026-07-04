import {
  Anchor,
  Badge,
  Button,
  Card,
  Group,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
  Tooltip,
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
import { DirectionBadge } from "@/components/DirectionBadge";
import { useFilters } from "@/components/FilterContext";
import { KpiTileSimple } from "@/components/KpiTileSimple";
import { PageState } from "@/components/PageState";
import { PillStrip } from "@/components/PillStrip";
import { PriceOverlayChart } from "@/components/PriceOverlayChart";
import { SectionIntro } from "@/components/SectionIntro";
import { TickerTimeline } from "@/components/TickerTimeline";
import { COPY } from "@/copy";
import {
  formatDate,
  formatSignedPercent,
  msnMoneyQuoteUrl,
  returnColor,
  searchForAlphaUrl,
  yahooFinanceQuoteUrl,
} from "@/utils/format";
import { rangeOpacity } from "@/utils/transactions";

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
    () =>
      (listQuery.data?.rows ?? []).map((r) => {
        const name = r.issuer_name?.trim();
        return {
          value: r.ticker,
          label: name ? `${r.ticker} — ${name}` : r.ticker,
        };
      }),
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
        <Group justify="space-between" align="flex-start" wrap="nowrap" gap="md">
          <SectionIntro
            kicker={COPY.tickers.kicker}
            title={COPY.tickers.title}
            copy={COPY.tickers.copy}
          />
          <Tooltip
            label={
              tickerForView
                ? `Open ${tickerForView} in SearchForAlpha Lab (new tab)`
                : "Pick a ticker first"
            }
            withArrow
          >
            <Button
              component="a"
              href={searchForAlphaUrl(tickerForView)}
              target="_blank"
              rel="noopener noreferrer"
              variant="light"
              color="orange"
              data-disabled={!tickerForView}
              aria-disabled={!tickerForView}
              onClick={(event) => {
                if (!tickerForView) event.preventDefault();
              }}
              data-testid="tickers-open-searchforalpha"
              style={{ flexShrink: 0 }}
            >
              Open in SearchForAlpha
            </Button>
          </Tooltip>
        </Group>

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

            {kpis ? (
              <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing="md">
                <KpiTileSimple
                  kpi={{
                    key: "weighted_return",
                    label: "Return (since trade)",
                    value: formatSignedPercent(kpis.return_pct),
                    detail:
                      kpis.return_pct == null
                        ? "Polygon cache empty"
                        : `Weighted over ${kpis.return_trade_count ?? 0} trade${
                            (kpis.return_trade_count ?? 0) === 1 ? "" : "s"
                          }`,
                  }}
                />
              </SimpleGrid>
            ) : null}

            <ChartCard collapsible title={COPY.tickers.whoTraded} testId="tickers-members-table">
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
                    {(profile.data?.members ?? []).map((row) => {
                      // Per-row trade-size bucket: same opacity ramp as the
                      // "By ticker" table, so the cell's color saturation
                      // captures the importance of the trade.
                      const rowOpacity = rangeOpacity(row.disclosed_range);
                      return (
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
                          <Table.Td
                            c="teal"
                            style={{
                              opacity: row.buy ? rowOpacity : 0.35,
                              fontWeight: 600,
                            }}
                            data-testid="tickers-who-traded-buys"
                          >
                            {row.buy}
                          </Table.Td>
                          <Table.Td
                            c="red"
                            style={{
                              opacity: row.sell ? rowOpacity : 0.35,
                              fontWeight: 600,
                            }}
                            data-testid="tickers-who-traded-sells"
                          >
                            {row.sell}
                          </Table.Td>
                          <Table.Td>{row.call}</Table.Td>
                          <Table.Td>{row.put}</Table.Td>
                          <Table.Td>{row.trades}</Table.Td>
                          <Table.Td>{row.disclosed_range}</Table.Td>
                          <Table.Td>{formatDate(row.first_trade)}</Table.Td>
                          <Table.Td>{formatDate(row.last_trade)}</Table.Td>
                        </Table.Tr>
                      );
                    })}
                  </Table.Tbody>
                </Table>
              </Table.ScrollContainer>
            </ChartCard>

            <ChartCard
              collapsible
              title="Trade history"
              caption="Most recent disclosures on this ticker. The Return column shows the market move from the trade date to today, using the local Polygon daily-bar cache."
              testId="tickers-trade-history"
            >
              {profile.data?.transactions && profile.data.transactions.length > 0 ? (
                <Table.ScrollContainer minWidth={1100}>
                  <Table striped data-testid="tickers-trade-history-table">
                    <Table.Thead>
                      <Table.Tr>
                        <Table.Th>Date</Table.Th>
                        <Table.Th>Member</Table.Th>
                        <Table.Th>Type</Table.Th>
                        <Table.Th>Amount</Table.Th>
                        <Table.Th>Price (trade)</Table.Th>
                        <Table.Th>Price (now)</Table.Th>
                        <Table.Th>Return</Table.Th>
                        <Table.Th>Est. P&amp;L</Table.Th>
                      </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                      {profile.data.transactions.map((row, i) => (
                        <Table.Tr
                          key={`${row.member}-${row.transaction_date}-${i}`}
                          data-testid="tickers-trade-history-row"
                        >
                          <Table.Td>{formatDate(row.transaction_date)}</Table.Td>
                          <Table.Td>{row.member}</Table.Td>
                          <Table.Td>
                            <DirectionBadge
                              label={row.transaction_type_label}
                              amountRangeRaw={row.amount_range_raw}
                              size="xs"
                            />
                          </Table.Td>
                          <Table.Td>
                            <Text
                              size="sm"
                              style={{ opacity: rangeOpacity(row.amount_range_raw) }}
                            >
                              {row.amount_range_raw}
                            </Text>
                          </Table.Td>
                          <Table.Td>
                            {row.price_trade ? `$${Number(row.price_trade).toFixed(2)}` : "—"}
                          </Table.Td>
                          <Table.Td>
                            {row.price_asof ? `$${Number(row.price_asof).toFixed(2)}` : "—"}
                          </Table.Td>
                          <Table.Td
                            c={returnColor(row.return_pct)}
                            fw={600}
                            data-testid="tickers-trade-history-return"
                          >
                            {row.is_non_equity ? (
                              <Tooltip
                                label="Non-equity asset (bond, treasury, etc.) — no daily market price."
                                withArrow
                              >
                                <Text component="span" c="dimmed" fw={400}>
                                  n/a
                                </Text>
                              </Tooltip>
                            ) : (
                              formatSignedPercent(row.return_pct)
                            )}
                          </Table.Td>
                          <Table.Td c={returnColor(row.est_pnl_usd)}>
                            {row.is_non_equity ? (
                              <Tooltip
                                label="Non-equity asset (bond, treasury, etc.) — no daily market price."
                                withArrow
                              >
                                <Text component="span" c="dimmed" fw={400}>
                                  n/a
                                </Text>
                              </Tooltip>
                            ) : row.est_pnl_usd == null ? (
                              "—"
                            ) : (
                              `${row.est_pnl_usd >= 0 ? "+" : ""}$${Math.abs(
                                row.est_pnl_usd,
                              ).toLocaleString(undefined, { maximumFractionDigits: 0 })}`
                            )}
                          </Table.Td>
                        </Table.Tr>
                      ))}
                    </Table.Tbody>
                  </Table>
                </Table.ScrollContainer>
              ) : (
                <Text c="dimmed">No disclosures in the active slice for this ticker.</Text>
              )}
            </ChartCard>

            <ChartCard collapsible title={COPY.tickers.priceOverlay} testId="tickers-price-overlay">
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

            <ChartCard collapsible title={COPY.tickers.memberTimeline} testId="tickers-member-timeline">
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

            <ChartCard collapsible title={COPY.tickers.cumulativeExposure} testId="tickers-cumulative">
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
