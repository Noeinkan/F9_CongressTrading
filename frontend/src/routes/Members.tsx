import {
  ActionIcon,
  Alert,
  Group,
  Loader,
  SegmentedControl,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Text,
  Tooltip,
} from "@mantine/core";
import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";

import {
  useMemberActivityTimeline,
  useMemberCommitteeRelevant,
  useMemberTickers,
  useMembersSummary,
} from "@/api/members";
import type { MemberActivityRow, TickerTimelineRow } from "@/api/types";
import { ChartCard } from "@/components/ChartCard";
import { DirectionBadge } from "@/components/DirectionBadge";
import { useFilters } from "@/components/FilterContext";
import { KpiTileSimple } from "@/components/KpiTileSimple";
import { MembersLeaderboardTable } from "@/components/MembersLeaderboardTable";
import { PageState } from "@/components/PageState";
import { RankBars } from "@/components/RankBars";
import { SectionIntro } from "@/components/SectionIntro";
import { TickerLink } from "@/components/TickerLink";
import { TickerTimeline } from "@/components/TickerTimeline";
import { COPY } from "@/copy";
import { formatCurrency, formatDate, formatSignedPercent, returnColor } from "@/utils/format";
import { rangeOpacity, parseRangeHigh } from "@/utils/transactions";

const COMMITTEE_VIEW = "committee_relevance";

function ChevronLeftIcon() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <polyline points="15 18 9 12 15 6" />
    </svg>
  );
}

function ChevronRightIcon() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <polyline points="9 18 15 12 9 6" />
    </svg>
  );
}

function quartersParam(quarters: string[]): string | undefined {
  if (quarters.length === 4) return undefined;
  return quarters.join(",");
}

function activityToTimelineRows(rows: MemberActivityRow[]): TickerTimelineRow[] {
  return rows.map((r) => {
    const high = parseRangeHigh(r.amount_range_raw);
    return {
      member: r.ticker,
      ticker: r.ticker,
      transaction_date: r.transaction_date,
      transaction_type: r.transaction_type,
      txn_type_label: r.transaction_type_label,
      amount_low: null,
      amount_high: high > 0 ? high : null,
      amount_range_raw: r.amount_range_raw,
      issuer_name: r.issuer_name,
    };
  });
}

export function Members() {
  const { lookback, quarters } = useFilters();
  const [searchParams, setSearchParams] = useSearchParams();

  const periodParams = useMemo(
    () => ({ lookback, quarters: quartersParam(quarters) }),
    [lookback, quarters],
  );

  const selectedMember = (searchParams.get("member") ?? "").trim();
  const tradeView = searchParams.get("view") === COMMITTEE_VIEW ? COMMITTEE_VIEW : "all";

  const { data, isLoading, isError } = useMembersSummary(periodParams);
  const memberTickers = useMemberTickers(selectedMember || null, periodParams);
  const committeeData = useMemberCommitteeRelevant(
    tradeView === COMMITTEE_VIEW && selectedMember ? selectedMember : null,
    periodParams,
  );
  const activityData = useMemberActivityTimeline(selectedMember || null, periodParams);

  // Deep-link (`?member=`) should paint immediately; only block on the
  // summary leaderboard when we still need it to browse.
  const deepLinked = selectedMember.length > 0;
  const pageLoading = deepLinked ? false : isLoading;
  const pageError = deepLinked ? false : isError;
  const pageReady = deepLinked ? true : (data?.ready ?? false);

  const memberOptions = useMemo(() => {
    const fromBoard = (data?.leaderboard ?? []).map((r) => r.member);
    if (selectedMember && !fromBoard.includes(selectedMember)) {
      return [selectedMember, ...fromBoard];
    }
    return fromBoard;
  }, [data?.leaderboard, selectedMember]);

  const setMember = (member: string | null) => {
    if (!member) return;
    const next = new URLSearchParams(searchParams);
    next.set("member", member);
    setSearchParams(next);
  };

  const selectedIndex = selectedMember ? memberOptions.indexOf(selectedMember) : -1;

  const goPrevMember = () => {
    if (memberOptions.length === 0) return;
    const next =
      selectedIndex <= 0
        ? memberOptions[memberOptions.length - 1]
        : memberOptions[selectedIndex - 1];
    if (next) setMember(next);
  };

  const goNextMember = () => {
    if (memberOptions.length === 0) return;
    const next =
      selectedIndex < 0 || selectedIndex >= memberOptions.length - 1
        ? memberOptions[0]
        : memberOptions[selectedIndex + 1];
    if (next) setMember(next);
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
    const counts = new Map<string, number>();
    for (const r of rows) {
      if (!r.ticker) continue;
      counts.set(r.ticker, (counts.get(r.ticker) ?? 0) + 1);
    }
    return Array.from(counts.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 12)
      .map(([ticker, count]) => ({ label: ticker, value: count }));
  }, [memberTickers.data?.rows]);

  return (
    <PageState isLoading={pageLoading} isError={pageError} ready={pageReady}>
      <Stack gap="md" data-testid="members-page">
          <SectionIntro
            kicker={COPY.members.kicker}
            title={COPY.members.title}
            copy={COPY.members.copy}
          />

          <ChartCard
            collapsible
            title={COPY.members.browse}
            caption="Full per-filer ranking for the active period slice. Click a row to open the profile below."
            testId="members-browse"
          >
            {isLoading && !data ? (
              <Group justify="center" py="md">
                <Loader size="sm" />
              </Group>
            ) : (
              <MembersLeaderboardTable
                rows={data?.leaderboard ?? []}
                selectedMember={selectedMember || undefined}
                onSelect={setMember}
                testId="members-leaderboard-table"
              />
            )}
          </ChartCard>

          <Stack gap={6}>
            <Group justify="space-between" align="baseline" gap="xs">
              <Text size="sm" fw={500}>
                {COPY.members.profile}
              </Text>
              {memberOptions.length > 0 ? (
                <Text size="xs" c="dimmed" data-testid="members-nav-position">
                  {selectedIndex >= 0 ? selectedIndex + 1 : "—"} / {memberOptions.length}
                </Text>
              ) : null}
            </Group>
            <Group gap="xs" wrap="nowrap" align="center">
              <ActionIcon
                variant="default"
                size="lg"
                aria-label="Previous member"
                onClick={goPrevMember}
                disabled={memberOptions.length === 0 || (isLoading && !selectedMember)}
                data-testid="members-prev"
              >
                <ChevronLeftIcon />
              </ActionIcon>
              <Select
                placeholder="Select a member"
                data={memberOptions}
                value={selectedMember || null}
                onChange={setMember}
                searchable
                disabled={isLoading && !selectedMember}
                data-testid="members-select"
                style={{ flex: 1 }}
              />
              <ActionIcon
                variant="default"
                size="lg"
                aria-label="Next member"
                onClick={goNextMember}
                disabled={memberOptions.length === 0 || (isLoading && !selectedMember)}
                data-testid="members-next"
              >
                <ChevronRightIcon />
              </ActionIcon>
            </Group>
          </Stack>

          {!selectedMember ? (
            <Text c="dimmed" data-testid="members-empty-profile">
              {COPY.members.emptyProfile}
            </Text>
          ) : null}

          {selectedMember && memberTickers.isLoading ? (
            <Stack align="center" py="xl" data-testid="members-profile-loading">
              <Loader size="md" />
              <Text size="sm" c="dimmed">
                Loading {selectedMember}…
              </Text>
            </Stack>
          ) : null}

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
                <ChartCard collapsible title={COPY.members.committeeCard} testId="members-committee-card">
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
                                <TickerLink ticker={row.ticker} />
                              </Table.Td>
                              <Table.Td>{row.sector}</Table.Td>
                              <Table.Td>{row.matching_committees}</Table.Td>
                              <Table.Td>
                                <DirectionBadge
                                  label={row.transaction_type_label}
                                  amountRangeRaw={row.amount_range_raw}
                                  size="xs"
                                />
                              </Table.Td>
                              <Table.Td>{formatDate(row.transaction_date)}</Table.Td>
                              <Table.Td>
                                <Text size="sm" style={{ opacity: rangeOpacity(row.amount_range_raw) }}>
                                  {row.amount_range_raw}
                                </Text>
                              </Table.Td>
                            </Table.Tr>
                          ))}
                        </Table.Tbody>
                      </Table>
                    </Table.ScrollContainer>
                  )}
                </ChartCard>
              ) : null}

              <ChartCard collapsible title={COPY.members.byTicker} testId="members-by-ticker">
                <Table.ScrollContainer minWidth={820}>
                  <Table striped data-testid="members-by-ticker-table">
                    <Table.Thead>
                      <Table.Tr>
                        <Table.Th>Date</Table.Th>
                        <Table.Th>Ticker</Table.Th>
                        <Table.Th>Issuer</Table.Th>
                        <Table.Th>Type</Table.Th>
                        <Table.Th>Amount</Table.Th>
                        <Table.Th>Filed</Table.Th>
                        <Table.Th>P&amp;L</Table.Th>
                        <Table.Th>P&amp;L %</Table.Th>
                      </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                      {(memberTickers.data?.rows ?? []).map((row, i) => {
                        // Bucket the row's disclosed range into an opacity in
                        // [0.35, 1] — the badge's color saturation tracks the
                        // trade-size importance, per the design spec.
                        return (
                          <Table.Tr key={`${row.ticker}-${row.transaction_date ?? ""}-${i}`}>
                            <Table.Td>{formatDate(row.transaction_date)}</Table.Td>
                            <Table.Td>
                              <TickerLink ticker={row.ticker} />
                            </Table.Td>
                            <Table.Td c="dimmed">{row.issuer_name || "—"}</Table.Td>
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
                          <Table.Td>{formatDate(row.filing_date ?? null)}</Table.Td>
                          <Table.Td
                            c={returnColor(row.est_pnl_usd ?? null)}
                            fw={600}
                            data-testid="members-by-ticker-pnl"
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
                              formatCurrency(row.est_pnl_usd ?? null)
                            )}
                          </Table.Td>
                          <Table.Td
                            c={returnColor(row.return_pct ?? null)}
                            fw={600}
                            data-testid="members-by-ticker-return"
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
                              formatSignedPercent(row.return_pct ?? null)
                            )}
                          </Table.Td>
                          </Table.Tr>
                        );
                      })}
                    </Table.Tbody>
                  </Table>
                </Table.ScrollContainer>
              </ChartCard>

              <ChartCard
                collapsible
                defaultCollapsed
                title={COPY.members.activity}
                testId="members-activity"
              >
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

              <ChartCard collapsible defaultCollapsed title={COPY.members.topTickers}>
                <RankBars
                  testId="members-top-tickers"
                  color="#c6922b"
                  linkKind="ticker"
                  rows={topTickerRows}
                />
              </ChartCard>
            </Stack>
          ) : null}
        </Stack>
    </PageState>
  );
}
