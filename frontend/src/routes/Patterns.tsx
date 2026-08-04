import { Select, SimpleGrid, Slider, Stack, Table, Text } from "@mantine/core";
import { useMemo, useState } from "react";

import {
  usePatternsCommitteeRelevant,
  usePatternsCoordinatedTransactions,
  usePatternsSummary,
} from "@/api/patterns";
import type { PatternsCoordinatedRow } from "@/api/types";
import { CallPutAreaChart } from "@/components/CallPutAreaChart";
import { CallPutRatioChart } from "@/components/CallPutRatioChart";
import { ChartCard } from "@/components/ChartCard";
import { useFilters } from "@/components/FilterContext";
import { MemberLink } from "@/components/MemberLink";
import { MemberNamesLinks } from "@/components/MemberNamesLinks";
import { PageState } from "@/components/PageState";
import { SectionIntro } from "@/components/SectionIntro";
import { TickerLink } from "@/components/TickerLink";
import { COPY } from "@/copy";
import { formatDate, formatNumber } from "@/utils/format";

const COMMITTEE_VIEW = "committee_relevance";

function quartersParam(quarters: string[]): string | undefined {
  if (quarters.length === 4) return undefined;
  return quarters.join(",");
}

/** Stable Select option / lookup key for a coordinated pattern row. */
export function coordinatedOptionKey(row: Pick<PatternsCoordinatedRow, "ticker" | "pattern" | "members">): string {
  return `${row.ticker} · ${row.pattern} · ${row.members} members`;
}

export function Patterns() {
  const { lookback, quarters } = useFilters();
  const [windowDays, setWindowDays] = useState(90);
  const [minMembers, setMinMembers] = useState(2);
  const [committeeMember, setCommitteeMember] = useState<string | null>(null);
  const [coordinatedKey, setCoordinatedKey] = useState<string | null>(null);

  const periodParams = useMemo(
    () => ({ lookback, quarters: quartersParam(quarters) }),
    [lookback, quarters],
  );

  const patternsParams = useMemo(
    () => ({
      ...periodParams,
      window_days: windowDays,
      min_members: minMembers,
    }),
    [periodParams, windowDays, minMembers],
  );

  const { data, isLoading, isError } = usePatternsSummary(patternsParams);
  const committeeDrill = usePatternsCommitteeRelevant(committeeMember, periodParams);

  const coordinatedSelection = useMemo(() => {
    if (!coordinatedKey || !data?.coordinated.length) return null;
    const row = data.coordinated.find((r) => coordinatedOptionKey(r) === coordinatedKey);
    if (!row) return null;
    return { ticker: row.ticker, pattern: row.pattern, window_days: windowDays };
  }, [coordinatedKey, data?.coordinated, windowDays]);

  const coordinatedTx = usePatternsCoordinatedTransactions(
    coordinatedSelection ? { ...periodParams, ...coordinatedSelection, limit: 50 } : null,
  );

  const coordinatedOptions = useMemo(
    () => (data?.coordinated ?? []).map(coordinatedOptionKey),
    [data?.coordinated],
  );

  return (
    <PageState isLoading={isLoading} isError={isError} ready={data?.ready ?? false}>
      {data ? (
        <Stack gap="md" data-testid="patterns-page">
          <SectionIntro
            kicker={COPY.patterns.kicker}
            title={COPY.patterns.title}
            copy={COPY.patterns.copy}
          />

          <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
            <Stack gap={4}>
              <Text size="sm" fw={500}>
                Lookback window (days): {windowDays}
              </Text>
              <Slider
                min={30}
                max={365}
                step={30}
                value={windowDays}
                onChange={setWindowDays}
                data-testid="patterns-window-slider"
              />
            </Stack>
            <Stack gap={4}>
              <Text size="sm" fw={500}>
                Min members for coordination: {minMembers}
              </Text>
              <Slider
                min={2}
                max={8}
                step={1}
                value={minMembers}
                onChange={setMinMembers}
                data-testid="patterns-min-members-slider"
              />
            </Stack>
          </SimpleGrid>

          <ChartCard collapsible title={COPY.patterns.committee} testId="patterns-committee">
            <Text size="sm" c="dimmed" mb="sm">
              {data.committee.coverage.members_mapped} members mapped ·{" "}
              {formatNumber(data.committee.coverage.member_coverage_pct, 1)}% member coverage ·{" "}
              {formatNumber(data.committee.coverage.sector_coverage_pct, 1)}% sector coverage
            </Text>
            <Table.ScrollContainer minWidth={900}>
              <Table striped data-testid="patterns-committee-table">
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Member</Table.Th>
                    <Table.Th>Chamber</Table.Th>
                    <Table.Th>Party</Table.Th>
                    <Table.Th>Total</Table.Th>
                    <Table.Th>Relevant</Table.Th>
                    <Table.Th>Relevance %</Table.Th>
                    <Table.Th>Top committee</Table.Th>
                    <Table.Th>Top sector</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {data.committee.summary.map((row) => (
                    <Table.Tr key={row.member}>
                      <Table.Td>
                        <MemberLink name={row.member} />
                      </Table.Td>
                      <Table.Td>{row.chamber}</Table.Td>
                      <Table.Td>{row.party}</Table.Td>
                      <Table.Td>{row.total_trades}</Table.Td>
                      <Table.Td>
                        <MemberLink
                          name={row.member}
                          extraParams={{ view: COMMITTEE_VIEW }}
                        >
                          {row.relevant_trades}
                        </MemberLink>
                      </Table.Td>
                      <Table.Td>{formatNumber(row.relevance_pct, 1)}%</Table.Td>
                      <Table.Td>{row.top_committee}</Table.Td>
                      <Table.Td>{row.top_sector}</Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>

            <Select
              mt="md"
              label="Member drill-down (committee overlap only)"
              placeholder="Select member"
              data={data.committee.members_with_overlap}
              value={committeeMember}
              onChange={setCommitteeMember}
              searchable
              clearable
              data-testid="patterns-committee-member-select"
            />

            {committeeMember && !committeeDrill.data?.rows.length ? (
              <Text c="dimmed" mt="md" data-testid="patterns-committee-drill-empty">
                {committeeDrill.isLoading
                  ? "Loading committee-relevant trades…"
                  : "No committee-relevant trades for this member."}
              </Text>
            ) : null}

            {committeeDrill.data?.rows.length ? (
              <Table.ScrollContainer minWidth={700} mt="md">
                <Table striped data-testid="patterns-committee-drill-table">
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
                    {committeeDrill.data.rows.map((row, i) => (
                      <Table.Tr key={`${row.ticker}-${i}`}>
                        <Table.Td>
                          <TickerLink ticker={row.ticker} />
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
            ) : !committeeMember ? (
              <Text c="dimmed" mt="md" data-testid="patterns-committee-drill-prompt">
                Select a member above to see overlapping committee trades.
              </Text>
            ) : null}
          </ChartCard>

          <ChartCard collapsible title={COPY.patterns.coordinated} testId="patterns-coordinated">
            <Table.ScrollContainer minWidth={800}>
              <Table striped data-testid="patterns-coordinated-table">
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Ticker</Table.Th>
                    <Table.Th>Pattern</Table.Th>
                    <Table.Th>Members</Table.Th>
                    <Table.Th>Names</Table.Th>
                    <Table.Th>Trades</Table.Th>
                    <Table.Th>From</Table.Th>
                    <Table.Th>To</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {data.coordinated.map((row) => (
                    <Table.Tr key={`${row.ticker}-${row.pattern}`}>
                      <Table.Td>
                        <TickerLink ticker={row.ticker} />
                      </Table.Td>
                      <Table.Td>{row.pattern}</Table.Td>
                      <Table.Td>{row.members}</Table.Td>
                      <Table.Td>
                        <MemberNamesLinks names={row.member_names} />
                      </Table.Td>
                      <Table.Td>{row.trades}</Table.Td>
                      <Table.Td>{formatDate(row.date_from)}</Table.Td>
                      <Table.Td>{formatDate(row.date_to)}</Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>

            <Select
              mt="md"
              label="Pattern drill-down"
              placeholder="Select pattern"
              data={coordinatedOptions}
              value={coordinatedKey}
              onChange={setCoordinatedKey}
              searchable
              clearable
              data-testid="patterns-coordinated-select"
            />

            {coordinatedKey && !coordinatedTx.data?.rows.length ? (
              <Text c="dimmed" mt="md" data-testid="patterns-coordinated-drill-empty">
                {coordinatedTx.isLoading
                  ? "Loading coordinated trades…"
                  : "No transactions for this pattern in the current window."}
              </Text>
            ) : null}

            {coordinatedTx.data?.rows.length ? (
              <Table.ScrollContainer minWidth={700} mt="md">
                <Table striped data-testid="patterns-coordinated-tx-table">
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Member</Table.Th>
                      <Table.Th>Ticker</Table.Th>
                      <Table.Th>Type</Table.Th>
                      <Table.Th>Traded</Table.Th>
                      <Table.Th>Amount</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {coordinatedTx.data.rows.map((row, i) => (
                      <Table.Tr key={`${row.member}-${i}`}>
                        <Table.Td>
                          <MemberLink name={row.member} />
                        </Table.Td>
                        <Table.Td>
                          <TickerLink ticker={row.ticker} />
                        </Table.Td>
                        <Table.Td>{row.transaction_type_label}</Table.Td>
                        <Table.Td>{formatDate(row.transaction_date)}</Table.Td>
                        <Table.Td>{row.amount_range_raw}</Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </Table.ScrollContainer>
            ) : !coordinatedKey ? (
              <Text c="dimmed" mt="md" data-testid="patterns-coordinated-drill-prompt">
                Select a pattern above to inspect its trades.
              </Text>
            ) : null}
          </ChartCard>

          <ChartCard collapsible title={COPY.patterns.callPut} testId="patterns-call-put">
            <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
              <CallPutAreaChart rows={data.call_put.monthly} />
              <Stack gap="xs">
                <CallPutRatioChart rows={data.call_put.ratio} />
                <Text size="sm" c="dimmed">
                  {COPY.patterns.callPutNote}
                </Text>
              </Stack>
            </SimpleGrid>
          </ChartCard>

          <ChartCard collapsible title={COPY.patterns.volumeSpikes} testId="patterns-volume">
            <Text size="sm" c="dimmed" mb="sm">
              {COPY.patterns.volumeCaption}
            </Text>
            <Table.ScrollContainer minWidth={700}>
              <Table striped data-testid="patterns-volume-table">
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Ticker</Table.Th>
                    <Table.Th>Recent</Table.Th>
                    <Table.Th>Recent/mo</Table.Th>
                    <Table.Th>Prior/mo</Table.Th>
                    <Table.Th>Spike</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {data.volume_anomalies.map((row) => (
                    <Table.Tr key={row.ticker}>
                      <Table.Td>
                        <TickerLink ticker={row.ticker} />
                      </Table.Td>
                      <Table.Td>{row.recent_disclosures}</Table.Td>
                      <Table.Td>{formatNumber(row.recent_per_month, 2)}</Table.Td>
                      <Table.Td>{formatNumber(row.prior_per_month, 2)}</Table.Td>
                      <Table.Td>{formatNumber(row.spike_ratio, 2)}</Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
          </ChartCard>

          <ChartCard collapsible title={COPY.patterns.bipartisan} testId="patterns-bipartisan">
            <Table.ScrollContainer minWidth={800}>
              <Table striped data-testid="patterns-bipartisan-table">
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Ticker</Table.Th>
                    <Table.Th>Members</Table.Th>
                    <Table.Th>Dem trades</Table.Th>
                    <Table.Th>Rep trades</Table.Th>
                    <Table.Th>Names</Table.Th>
                    <Table.Th>From</Table.Th>
                    <Table.Th>To</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {data.bipartisan.map((row) => (
                    <Table.Tr key={row.ticker}>
                      <Table.Td>
                        <TickerLink ticker={row.ticker} />
                      </Table.Td>
                      <Table.Td>{row.members}</Table.Td>
                      <Table.Td>{row.democrat_trades}</Table.Td>
                      <Table.Td>{row.republican_trades}</Table.Td>
                      <Table.Td>
                        <MemberNamesLinks names={row.member_names} />
                      </Table.Td>
                      <Table.Td>{formatDate(row.date_from)}</Table.Td>
                      <Table.Td>{formatDate(row.date_to)}</Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
          </ChartCard>
        </Stack>
      ) : null}
    </PageState>
  );
}
