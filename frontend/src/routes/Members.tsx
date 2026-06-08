import {
  Alert,
  Anchor,
  SegmentedControl,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Text,
} from "@mantine/core";
import { useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";

import {
  useMemberActivityTimeline,
  useMemberCommitteeRelevant,
  useMemberTickers,
  useMembersSummary,
} from "@/api/members";
import type { MemberActivityRow, TickerTimelineRow } from "@/api/types";
import { ChartCard } from "@/components/ChartCard";
import { useFilters } from "@/components/FilterContext";
import { KpiTileSimple } from "@/components/KpiTileSimple";
import { PageState } from "@/components/PageState";
import { RankBars } from "@/components/RankBars";
import { SectionIntro } from "@/components/SectionIntro";
import { TickerTimeline } from "@/components/TickerTimeline";
import { COPY } from "@/copy";
import { formatDate, formatDisclosedRange } from "@/utils/format";

const COMMITTEE_VIEW = "committee_relevance";

function quartersParam(quarters: string[]): string | undefined {
  if (quarters.length === 4) return undefined;
  return quarters.join(",");
}

function activityToTimelineRows(rows: MemberActivityRow[]): TickerTimelineRow[] {
  return rows.map((r) => ({
    member: r.ticker,
    ticker: r.ticker,
    transaction_date: r.transaction_date,
    transaction_type: r.transaction_type,
    txn_type_label: r.transaction_type_label,
    amount_low: null,
    amount_high: null,
    amount_range_raw: r.amount_range_raw,
    issuer_name: r.issuer_name,
  }));
}

export function Members() {
  const { lookback, quarters } = useFilters();
  const [searchParams, setSearchParams] = useSearchParams();

  const periodParams = useMemo(
    () => ({ lookback, quarters: quartersParam(quarters) }),
    [lookback, quarters],
  );

  const selectedMember = searchParams.get("member") ?? "";
  const tradeView = searchParams.get("view") === COMMITTEE_VIEW ? COMMITTEE_VIEW : "all";

  const { data, isLoading, isError } = useMembersSummary(periodParams);
  const memberTickers = useMemberTickers(selectedMember || null, periodParams);
  const committeeData = useMemberCommitteeRelevant(
    tradeView === COMMITTEE_VIEW && selectedMember ? selectedMember : null,
    periodParams,
  );
  const activityData = useMemberActivityTimeline(selectedMember || null, periodParams);

  const memberOptions = useMemo(
    () => (data?.leaderboard ?? []).map((r) => r.member),
    [data?.leaderboard],
  );

  const setMember = (member: string | null) => {
    if (!member) return;
    const next = new URLSearchParams(searchParams);
    next.set("member", member);
    setSearchParams(next);
  };

  const setTradeView = (value: string) => {
    const next = new URLSearchParams(searchParams);
    if (value === COMMITTEE_VIEW) {
      next.set("view", COMMITTEE_VIEW);
    } else {
      next.delete("view");
    }
    setSearchParams(next);
  };

  const kpis = memberTickers.data?.kpis;
  const topTickerRows = useMemo(() => {
    const rows = memberTickers.data?.rows ?? [];
    return [...rows]
      .sort((a, b) => b.trades - a.trades)
      .slice(0, 12)
      .map((r) => ({ label: r.ticker, value: r.trades }));
  }, [memberTickers.data?.rows]);

  return (
    <PageState isLoading={isLoading} isError={isError} ready={data?.ready ?? false}>
      {data ? (
        <Stack gap="md" data-testid="members-page">
          <SectionIntro
            kicker={COPY.members.kicker}
            title={COPY.members.title}
            copy={COPY.members.copy}
          />

          <ChartCard title={COPY.members.leaderboard} testId="members-leaderboard">
            <Table.ScrollContainer minWidth={800}>
              <Table striped highlightOnHover data-testid="members-leaderboard-table">
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
                  {data.leaderboard.map((row) => (
                    <Table.Tr
                      key={row.member}
                      style={{ cursor: "pointer" }}
                      onClick={() => setMember(row.member)}
                      data-testid="members-leaderboard-row"
                    >
                      <Table.Td fw={selectedMember === row.member ? 700 : 400}>{row.member}</Table.Td>
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
          </ChartCard>

          <Select
            label={COPY.members.profile}
            placeholder="Select a member"
            data={memberOptions}
            value={selectedMember || null}
            onChange={setMember}
            searchable
            data-testid="members-select"
          />

          {selectedMember && kpis ? (
            <Stack gap="md" data-testid="members-profile">
              <SegmentedControl
                value={tradeView}
                onChange={setTradeView}
                data={[
                  { label: COPY.members.allTrades, value: "all" },
                  { label: COPY.members.committeeRelevant, value: COMMITTEE_VIEW },
                ]}
                data-testid="members-trade-view"
              />

              <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing="md">
                <KpiTileSimple
                  kpi={{
                    key: "trades",
                    label: "Trades",
                    value: kpis.trades,
                    sparkline: kpis.sparklines.transactions,
                  }}
                />
                <KpiTileSimple
                  kpi={{
                    key: "tickers",
                    label: "Tickers",
                    value: kpis.tickers,
                    sparkline: kpis.sparklines.tickers,
                  }}
                />
                <KpiTileSimple
                  kpi={{
                    key: "range",
                    label: "Disclosed range",
                    value: kpis.disclosed_range,
                    sparkline: kpis.sparklines.disclosed_amount_high,
                  }}
                />
                <KpiTileSimple
                  kpi={{
                    key: "meta",
                    label: "Chamber / party",
                    value: `${kpis.chamber || "—"} · ${kpis.party || "—"}`,
                    detail: kpis.state,
                  }}
                />
              </SimpleGrid>

              {tradeView === COMMITTEE_VIEW ? (
                <ChartCard title={COPY.members.committeeCard} testId="members-committee-card">
                  {!committeeData.data?.assignments_loaded ? (
                    <Text c="dimmed">Committee assignments not loaded.</Text>
                  ) : committeeData.data.rows.length === 0 ? (
                    <Text c="dimmed">No committee-relevant trades for this member.</Text>
                  ) : (
                    <Table.ScrollContainer minWidth={700}>
                      <Table striped data-testid="members-committee-table">
                        <Table.Thead>
                          <Table.Tr>
                            <Table.Th>Ticker</Table.Th>
                            <Table.Th>Sector</Table.Th>
                            <Table.Th>Committees</Table.Th>
                            <Table.Th>Type</Table.Th>
                            <Table.Th>Traded</Table.Th>
                            <Table.Th>Amount</Table.Th>
                          </Table.Tr>
                        </Table.Thead>
                        <Table.Tbody>
                          {committeeData.data.rows.map((row, i) => (
                            <Table.Tr key={`${row.ticker}-${i}`}>
                              <Table.Td>
                                <Anchor
                                  component={Link}
                                  to={`/tickers?ticker=${encodeURIComponent(row.ticker)}`}
                                  size="sm"
                                >
                                  {row.ticker}
                                </Anchor>
                              </Table.Td>
                              <Table.Td>{row.sector}</Table.Td>
                              <Table.Td>{row.matching_committees}</Table.Td>
                              <Table.Td>{row.transaction_type_label}</Table.Td>
                              <Table.Td>{formatDate(row.transaction_date)}</Table.Td>
                              <Table.Td>{row.amount_range_raw}</Table.Td>
                            </Table.Tr>
                          ))}
                        </Table.Tbody>
                      </Table>
                    </Table.ScrollContainer>
                  )}
                </ChartCard>
              ) : null}

              <ChartCard title={COPY.members.byTicker} testId="members-by-ticker">
                <Table.ScrollContainer minWidth={900}>
                  <Table striped data-testid="members-by-ticker-table">
                    <Table.Thead>
                      <Table.Tr>
                        <Table.Th>Ticker</Table.Th>
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
                      {(memberTickers.data?.rows ?? []).map((row) => (
                        <Table.Tr key={row.ticker}>
                          <Table.Td>
                            <Anchor
                              component={Link}
                              to={`/tickers?ticker=${encodeURIComponent(row.ticker)}`}
                              size="sm"
                            >
                              {row.ticker}
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

              <ChartCard title={COPY.members.activity} testId="members-activity">
                {activityData.data?.truncated ? (
                  <Alert color="gray" variant="light" mb="sm" data-testid="members-activity-truncate">
                    {activityData.data.truncate_note}
                  </Alert>
                ) : null}
                <TickerTimeline
                  rows={activityToTimelineRows(activityData.data?.rows ?? [])}
                  yField="ticker"
                  yOrder={activityData.data?.tickers}
                  testId="members-activity-chart"
                />
              </ChartCard>

              <ChartCard title={COPY.members.topTickers}>
                <RankBars testId="members-top-tickers" color="#c6922b" rows={topTickerRows} />
              </ChartCard>
            </Stack>
          ) : null}
        </Stack>
      ) : null}
    </PageState>
  );
}
