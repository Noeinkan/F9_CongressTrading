import { Badge, Card, SimpleGrid, Stack, Table, Text, Title } from "@mantine/core";
import { useMemo } from "react";

import { useSenateSummary } from "@/api/senate";
import type { SenateSummaryResponse } from "@/api/types";
import { ChartCard } from "@/components/ChartCard";
import { useFilters } from "@/components/FilterContext";
import { KpiTile, type KpiTileSpec } from "@/components/KpiTile";
import { MemberLink } from "@/components/MemberLink";
import { MembersLeaderboardTable } from "@/components/MembersLeaderboardTable";
import { MonthlyActivityChart } from "@/components/MonthlyActivityChart";
import { NetTradeChart } from "@/components/NetTradeChart";
import { PageState } from "@/components/PageState";
import { RankBars } from "@/components/RankBars";
import { SectionIntro } from "@/components/SectionIntro";
import { TickerLink } from "@/components/TickerLink";
import { COPY } from "@/copy";
import { formatCount, formatDate } from "@/utils/format";
import { classifyTransaction, directionColor } from "@/utils/transactions";

const LATEST_ROWS = 25;

function quartersParam(quarters: string[]): string | undefined {
  if (quarters.length === 4) return undefined;
  return quarters.join(",");
}

/** "R-UT" from "Republican" + "UT"; whichever half is known. */
function partyState(party: string, state: string): string {
  const initial = party && party !== "Unknown" ? party.charAt(0) : "";
  return [initial, state].filter(Boolean).join("-");
}

function dateSpan(from: string | null, to: string | null): string {
  if (!from && !to) return "—";
  if (!from || !to || from === to) return formatDate(from ?? to);
  return `${formatDate(from)} – ${formatDate(to)}`;
}

/** Home's KPIs relabelled for senators, minus the review queue, plus lateness. */
function senateKpis(data: SenateSummaryResponse): KpiTileSpec[] {
  const relabel: Record<string, string> = { members: "Senators" };
  const base = data.kpis
    .filter((kpi) => kpi.key !== "open_reviews")
    .map((kpi) => ({ ...kpi, label: relabel[kpi.key] ?? kpi.label }));
  const t = data.timeliness;
  const median = t.median_delay_days == null ? "" : ` · median ${t.median_delay_days} days to file`;
  return [
    ...base,
    {
      key: "late",
      label: "Filed late",
      value: t.late_share_label,
      detail: `${formatCount(t.late_trades)} of ${formatCount(t.dated_trades)} trades past the ${t.deadline_days}-day deadline${median}`,
    },
  ];
}

export function Senate() {
  const { lookback, quarters } = useFilters();
  const periodParams = useMemo(
    () => ({ lookback, quarters: quartersParam(quarters) }),
    [lookback, quarters],
  );
  const { data, isLoading, isError } = useSenateSummary(periodParams);

  const kpis = useMemo(() => (data ? senateKpis(data) : []), [data]);
  const latest = useMemo(
    () => (data?.latest_transactions ?? []).slice(0, LATEST_ROWS),
    [data?.latest_transactions],
  );

  const nothingIngested = data != null && data.senate_rows_all_time === 0;
  const nothingInPeriod = data != null && !nothingIngested && data.hero.total_transactions === 0;

  return (
    <PageState isLoading={isLoading} isError={isError} ready={data?.ready ?? false}>
      {data ? (
        <Stack gap="md" data-testid="senate-page">
          <SectionIntro
            kicker="Senate"
            title="What senators are trading"
            copy="Periodic transaction reports filed by U.S. senators on efdsearch.senate.gov, loaded every night. Figures follow the period selected in the sidebar."
          />

          {nothingIngested ? (
            <Card withBorder radius="md" padding="lg" data-testid="senate-empty">
              <Stack gap="xs">
                <Title order={4}>No Senate filings ingested yet</Title>
                <Text c="dimmed" size="sm">
                  The nightly job downloads them when SENATE_EFD_AUTO_DOWNLOAD=1 is set on the
                  server. To load them by hand, run:
                </Text>
                <Text size="sm" style={{ fontFamily: "var(--mantine-font-family-monospace)" }}>
                  python -m src.main download-senate &amp;&amp; python -m src.main ingest-senate
                </Text>
              </Stack>
            </Card>
          ) : nothingInPeriod ? (
            <Card withBorder radius="md" padding="lg" data-testid="senate-empty-period">
              <Text c="dimmed">
                No Senate trades in the selected period. Widen the lookback in the sidebar to see
                the {formatCount(data.senate_rows_all_time)} loaded so far.
              </Text>
            </Card>
          ) : (
            <>
              <Card withBorder radius="md" padding="md" data-testid="senate-header">
                <SimpleGrid cols={{ base: 1, sm: 2, md: 4 }} spacing="md">
                  <Stack gap={2}>
                    <Text size="xs" c="dimmed" tt="uppercase" fw={700}>
                      Senators with trades
                    </Text>
                    <Text fw={700} size="lg">
                      {formatCount(data.coverage.senators)}
                    </Text>
                  </Stack>
                  <Stack gap={2}>
                    <Text size="xs" c="dimmed" tt="uppercase" fw={700}>
                      Filings
                    </Text>
                    <Text fw={700} size="lg">
                      {formatCount(data.coverage.filings)}
                    </Text>
                  </Stack>
                  <Stack gap={2}>
                    <Text size="xs" c="dimmed" tt="uppercase" fw={700}>
                      Filed between
                    </Text>
                    <Text fw={600}>
                      {dateSpan(data.coverage.first_filing, data.coverage.latest_filing)}
                    </Text>
                  </Stack>
                  <Stack gap={2}>
                    <Text size="xs" c="dimmed" tt="uppercase" fw={700}>
                      Original filings
                    </Text>
                    <Text size="sm" c="dimmed" data-testid="senate-no-pdf-note">
                      No PDF links: the Senate site opens a report only after you accept its
                      terms. Open a senator for the detail.
                    </Text>
                  </Stack>
                </SimpleGrid>
              </Card>

              <SimpleGrid cols={{ base: 1, sm: 2, lg: 5 }} spacing="md">
                {kpis.map((kpi) => (
                  <KpiTile key={kpi.key} kpi={kpi} />
                ))}
              </SimpleGrid>

              <ChartCard
                collapsible
                title="Latest trades"
                caption="Most recent Senate transactions in the period. Click a name or ticker to open its profile."
                testId="senate-latest"
              >
                <Table.ScrollContainer minWidth={700}>
                  <Table striped highlightOnHover data-testid="senate-latest-table">
                    <Table.Thead>
                      <Table.Tr>
                        <Table.Th>Senator</Table.Th>
                        <Table.Th>Ticker</Table.Th>
                        <Table.Th>Type</Table.Th>
                        <Table.Th>Traded</Table.Th>
                        <Table.Th>Filed</Table.Th>
                        <Table.Th>Range</Table.Th>
                      </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                      {latest.map((row, i) => (
                        <Table.Tr
                          key={`${row.member}-${row.transaction_date}-${i}`}
                          data-testid="senate-latest-row"
                        >
                          <Table.Td>
                            <MemberLink name={row.member} />
                          </Table.Td>
                          <Table.Td>
                            {row.ticker ? (
                              <TickerLink ticker={row.ticker} fw={500} />
                            ) : (
                              <Text size="sm">—</Text>
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
                              color={directionColor(classifyTransaction(row.transaction_type_label))}
                            >
                              {row.transaction_type_label || "—"}
                            </Badge>
                          </Table.Td>
                          <Table.Td>{formatDate(row.transaction_date)}</Table.Td>
                          <Table.Td>{formatDate(row.filing_date)}</Table.Td>
                          <Table.Td>{row.amount_range_raw || "—"}</Table.Td>
                        </Table.Tr>
                      ))}
                    </Table.Tbody>
                  </Table>
                </Table.ScrollContainer>
              </ChartCard>

              <ChartCard collapsible title="Monthly activity" caption={COPY.home.monthlyActivity}>
                <MonthlyActivityChart rows={data.monthly_activity} />
              </ChartCard>

              <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
                <ChartCard collapsible title="Most active senators">
                  <RankBars
                    testId="senate-top-members"
                    color="#20344a"
                    linkKind="member"
                    rows={data.top_members.map((r) => ({
                      label: r.member ?? "",
                      value: r.transactions,
                    }))}
                  />
                </ChartCard>
                <ChartCard collapsible title="Most traded tickers">
                  <RankBars
                    testId="senate-top-tickers"
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
                title="Filings"
                caption="One row per report, newest first: how many trades it disclosed and when they happened."
                testId="senate-filings"
              >
                <Table.ScrollContainer minWidth={760}>
                  <Table striped highlightOnHover data-testid="senate-filings-table">
                    <Table.Thead>
                      <Table.Tr>
                        <Table.Th>Filed</Table.Th>
                        <Table.Th>Senator</Table.Th>
                        <Table.Th>Trades</Table.Th>
                        <Table.Th>Tickers</Table.Th>
                        <Table.Th>Disclosed range</Table.Th>
                        <Table.Th>Traded</Table.Th>
                      </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                      {data.filings.map((f) => (
                        <Table.Tr key={`${f.member}-${f.doc_id}`} data-testid="senate-filing-row">
                          <Table.Td>{formatDate(f.filing_date)}</Table.Td>
                          <Table.Td>
                            <MemberLink name={f.member} />{" "}
                            <Text span size="xs" c="dimmed">
                              {partyState(f.party, f.state)}
                            </Text>
                          </Table.Td>
                          <Table.Td>{formatCount(f.trades)}</Table.Td>
                          <Table.Td>{formatCount(f.tickers)}</Table.Td>
                          <Table.Td>{f.disclosed_range}</Table.Td>
                          <Table.Td>{dateSpan(f.traded_from, f.traded_to)}</Table.Td>
                        </Table.Tr>
                      ))}
                    </Table.Tbody>
                  </Table>
                </Table.ScrollContainer>
              </ChartCard>

              <ChartCard
                collapsible
                title="Late filers"
                caption={`Senators with trades disclosed more than ${data.timeliness.deadline_days} days after they happened, the STOCK Act deadline.`}
                testId="senate-late"
              >
                {data.timeliness.late_filers.length === 0 ? (
                  <Text c="dimmed" data-testid="senate-late-none">
                    Every dated trade in the period was filed within the deadline.
                  </Text>
                ) : (
                  <Table.ScrollContainer minWidth={520}>
                    <Table striped data-testid="senate-late-table">
                      <Table.Thead>
                        <Table.Tr>
                          <Table.Th>Senator</Table.Th>
                          <Table.Th>Late trades</Table.Th>
                          <Table.Th>Worst</Table.Th>
                        </Table.Tr>
                      </Table.Thead>
                      <Table.Tbody>
                        {data.timeliness.late_filers.map((r) => (
                          <Table.Tr key={r.member} data-testid="senate-late-row">
                            <Table.Td>
                              <MemberLink name={r.member} />
                            </Table.Td>
                            <Table.Td>
                              {formatCount(r.late_trades)} of {formatCount(r.trades)}
                            </Table.Td>
                            <Table.Td>{formatCount(r.worst_days_late)} days late</Table.Td>
                          </Table.Tr>
                        ))}
                      </Table.Tbody>
                    </Table>
                  </Table.ScrollContainer>
                )}
              </ChartCard>

              <ChartCard
                collapsible
                title="Net trade amount"
                caption="Net signed dollar flow per ticker across senators — green is net buying, red is net selling."
              >
                {data.net_trade_amounts.length === 0 ? (
                  <Text c="dimmed">No resolved tickers with directional amounts in the period.</Text>
                ) : (
                  <NetTradeChart rows={data.net_trade_amounts} />
                )}
              </ChartCard>

              <ChartCard
                collapsible
                title="Senators leaderboard"
                caption="Every senator with trades in the period. Click a name to open the profile."
                testId="senate-leaderboard"
              >
                <MembersLeaderboardTable
                  rows={data.members_leaderboard}
                  testId="senate-leaderboard-table"
                />
              </ChartCard>
            </>
          )}
        </Stack>
      ) : null}
    </PageState>
  );
}
