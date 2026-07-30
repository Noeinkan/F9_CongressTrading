import {
  Anchor,
  Button,
  Checkbox,
  Group,
  Pagination,
  SimpleGrid,
  Stack,
  Table,
  Text,
  TextInput,
} from "@mantine/core";
import { useMemo, useState, useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { ApiError } from "@/api/client";
import {
  useAcceptReviewItem,
  useDismissReviewItem,
  useResolveReviewItem,
  useReviewSummary,
} from "@/api/review";
import type { ReviewRow } from "@/api/types";
import { BarChart } from "@/components/BarChart";
import { ChartCard } from "@/components/ChartCard";
import { useFilters } from "@/components/FilterContext";
import { KpiTileSimple } from "@/components/KpiTileSimple";
import { PageState } from "@/components/PageState";
import { SectionIntro } from "@/components/SectionIntro";
import { COPY } from "@/copy";
import { formatDate, formatNumber } from "@/utils/format";

function quartersParam(quarters: string[]): string | undefined {
  if (quarters.length === 4) return undefined;
  return quarters.join(",");
}

function mutationErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const body = error.body;
    if (body && typeof body === "object" && "detail" in body) {
      const detail = (body as { detail: unknown }).detail;
      if (typeof detail === "string") return detail;
    }
    return error.message;
  }
  if (error instanceof Error) return error.message;
  return "Action failed";
}

function ReviewRowActions({
  row,
  applyToAsset,
  canMutate,
}: {
  row: ReviewRow;
  applyToAsset: boolean;
  canMutate: boolean;
}) {
  const transactionId = row.transaction_id ?? null;
  const [draftTicker, setDraftTicker] = useState(row.ticker || "");
  const [localError, setLocalError] = useState<string | null>(null);

  const resolveMutation = useResolveReviewItem();
  const acceptMutation = useAcceptReviewItem();
  const dismissMutation = useDismissReviewItem();

  const busy =
    resolveMutation.isPending || acceptMutation.isPending || dismissMutation.isPending;

  if (!canMutate || transactionId == null) {
    return (
      <Text size="xs" c="dimmed">
        Read-only
      </Text>
    );
  }

  const run = async (action: () => Promise<unknown>) => {
    setLocalError(null);
    try {
      await action();
    } catch (error) {
      setLocalError(mutationErrorMessage(error));
    }
  };

  return (
    <Stack gap={4} maw={280}>
      <Group gap={6} wrap="nowrap">
        <TextInput
          size="xs"
          w={88}
          placeholder="Ticker"
          value={draftTicker}
          onChange={(e) => setDraftTicker(e.currentTarget.value.toUpperCase())}
          disabled={busy}
          aria-label={`Ticker for ${row.asset_name_raw || row.member}`}
          data-testid={`review-ticker-input-${transactionId}`}
        />
        <Button
          size="xs"
          variant="filled"
          disabled={busy || !draftTicker.trim()}
          loading={resolveMutation.isPending}
          onClick={() =>
            void run(() =>
              resolveMutation.mutateAsync({
                transactionId,
                ticker: draftTicker.trim(),
                applyToAsset,
              }),
            )
          }
          data-testid={`review-resolve-${transactionId}`}
        >
          Save
        </Button>
        {row.ticker ? (
          <Button
            size="xs"
            variant="light"
            disabled={busy}
            loading={acceptMutation.isPending}
            onClick={() =>
              void run(() =>
                acceptMutation.mutateAsync({
                  transactionId,
                  applyToAsset,
                }),
              )
            }
            data-testid={`review-accept-${transactionId}`}
          >
            Accept
          </Button>
        ) : null}
        <Button
          size="xs"
          variant="subtle"
          color="gray"
          disabled={busy}
          loading={dismissMutation.isPending}
          onClick={() => void run(() => dismissMutation.mutateAsync(transactionId))}
          data-testid={`review-dismiss-${transactionId}`}
        >
          Dismiss
        </Button>
      </Group>
      {localError ? (
        <Text size="xs" c="red" data-testid={`review-action-error-${transactionId}`}>
          {localError}
        </Text>
      ) : null}
    </Stack>
  );
}

export function Review() {
  const { lookback, quarters } = useFilters();
  const [searchParams, setSearchParams] = useSearchParams();
  const page = Number(searchParams.get("page") ?? "1") || 1;
  const pageSize = 40;
  const [applyToAsset, setApplyToAsset] = useState(false);

  const periodParams = useMemo(
    () => ({ lookback, quarters: quartersParam(quarters) }),
    [lookback, quarters],
  );

  const reviewParams = useMemo(
    () => ({
      ...periodParams,
      limit: pageSize,
      offset: (page - 1) * pageSize,
    }),
    [periodParams, page],
  );

  const { data, isLoading, isError } = useReviewSummary(reviewParams);
  const totalPages = data ? Math.max(1, Math.ceil(data.total / pageSize)) : 0;
  const canMutate = Boolean(data?.review_source?.startsWith("sqlite:"));

  useEffect(() => {
    if (!data) return;
    const tp = Math.max(1, Math.ceil(data.total / pageSize));
    if (page > tp) {
      const next = new URLSearchParams(searchParams);
      next.set("page", String(tp));
      setSearchParams(next, { replace: true });
    }
  }, [data, page, pageSize, searchParams, setSearchParams]);

  return (
    <PageState isLoading={isLoading} isError={isError} ready={data?.ready ?? false}>
      {data ? (
        <Stack gap="md" data-testid="review-page">
          <SectionIntro
            kicker={COPY.review.kicker}
            title={COPY.review.title}
            copy={COPY.review.copy}
          />

          <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="md">
            <KpiTileSimple
              kpi={{
                key: "open",
                label: "Open records",
                value: data.kpis.open_count.toLocaleString(),
                detail: `${data.kpis.total_count.toLocaleString()} total`,
              }}
            />
            <KpiTileSimple
              kpi={{
                key: "total",
                label: "Total records",
                value: data.kpis.total_count.toLocaleString(),
                detail: data.review_source,
              }}
            />
            <KpiTileSimple
              kpi={{
                key: "confidence",
                label: "High confidence",
                value: data.kpis.high_confidence_label,
                detail: "Score ≥ 70%",
              }}
            />
          </SimpleGrid>

          <ChartCard collapsible title={COPY.review.recordsCard} testId="review-records-card">
            {data.kpis.total_count === 0 ? (
              <Text c="dimmed">No records currently require review for the selected filter.</Text>
            ) : (
              <Stack gap="lg">
                <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
                  <Stack gap="xs">
                    <Text fw={600}>{COPY.review.byReason}</Text>
                    <Text size="sm" c="dimmed">
                      {COPY.review.reasonCaption}
                    </Text>
                    <BarChart
                      testId="review-by-reason"
                      color="#20344a"
                      rows={data.kpis.by_reason.map((r) => ({
                        label: r.reason || "—",
                        value: r.records,
                      }))}
                    />
                  </Stack>
                  <Stack gap="xs">
                    <Text fw={600}>{COPY.review.byStatus}</Text>
                    <Text size="sm" c="dimmed">
                      {COPY.review.statusCaption}
                    </Text>
                    <BarChart
                      testId="review-by-status"
                      color="#a64b2a"
                      rows={data.kpis.by_status.map((r) => ({
                        label: r.status || "—",
                        value: r.records,
                      }))}
                    />
                  </Stack>
                </SimpleGrid>

                <Stack gap="xs">
                  <Group justify="space-between" align="flex-end">
                    <Stack gap={2}>
                      <Text fw={600}>{COPY.review.summaryTable}</Text>
                      <Text size="sm" c="dimmed">
                        {COPY.review.actionsCaption}
                      </Text>
                    </Stack>
                    <Checkbox
                      label={COPY.review.applyToAsset}
                      checked={applyToAsset}
                      onChange={(e) => setApplyToAsset(e.currentTarget.checked)}
                      disabled={!canMutate}
                      data-testid="review-apply-to-asset"
                    />
                  </Group>
                  {!canMutate ? (
                    <Text size="sm" c="dimmed">
                      Triage actions need a live SQLite review queue (current source:{" "}
                      {data.review_source}).
                    </Text>
                  ) : null}
                  <Table.ScrollContainer minWidth={1100}>
                    <Table striped data-testid="review-summary-table">
                      <Table.Thead>
                        <Table.Tr>
                          <Table.Th>Reason</Table.Th>
                          <Table.Th>Status</Table.Th>
                          <Table.Th>Member</Table.Th>
                          <Table.Th>Ticker</Table.Th>
                          <Table.Th>Type</Table.Th>
                          <Table.Th>Amount</Table.Th>
                          <Table.Th>Confidence</Table.Th>
                          <Table.Th>Actions</Table.Th>
                        </Table.Tr>
                      </Table.Thead>
                      <Table.Tbody>
                        {data.rows.map((row, i) => (
                          <Table.Tr
                            key={`${row.transaction_id ?? "row"}-${row.member}-${row.transaction_date}-${i}`}
                          >
                            <Table.Td>{row.reason}</Table.Td>
                            <Table.Td>{row.status}</Table.Td>
                            <Table.Td>
                              <Anchor
                                component={Link}
                                to={`/members?member=${encodeURIComponent(row.member)}`}
                                size="sm"
                              >
                                {row.member}
                              </Anchor>
                            </Table.Td>
                            <Table.Td>
                              {row.ticker ? (
                                <Anchor
                                  component={Link}
                                  to={`/tickers?ticker=${encodeURIComponent(row.ticker)}`}
                                  size="sm"
                                >
                                  {row.ticker}
                                </Anchor>
                              ) : (
                                "—"
                              )}
                            </Table.Td>
                            <Table.Td>{row.transaction_type_label ?? row.transaction_type}</Table.Td>
                            <Table.Td>{row.amount_range_raw}</Table.Td>
                            <Table.Td>{formatNumber(row.confidence_score, 2)}</Table.Td>
                            <Table.Td>
                              <ReviewRowActions
                                row={row}
                                applyToAsset={applyToAsset}
                                canMutate={canMutate}
                              />
                            </Table.Td>
                          </Table.Tr>
                        ))}
                      </Table.Tbody>
                    </Table>
                  </Table.ScrollContainer>
                </Stack>

                <Stack gap="xs">
                  <Text fw={600}>{COPY.review.transactionDetail}</Text>
                  <Table.ScrollContainer minWidth={900}>
                    <Table striped data-testid="review-transaction-table">
                      <Table.Thead>
                        <Table.Tr>
                          <Table.Th>Ticker</Table.Th>
                          <Table.Th>Stock</Table.Th>
                          <Table.Th>Type</Table.Th>
                          <Table.Th>Member</Table.Th>
                          <Table.Th>Filed</Table.Th>
                          <Table.Th>Traded</Table.Th>
                        </Table.Tr>
                      </Table.Thead>
                      <Table.Tbody>
                        {data.rows.slice(0, 40).map((row, i) => (
                          <Table.Tr key={`tx-${row.transaction_id ?? i}`}>
                            <Table.Td>{row.ticker || "—"}</Table.Td>
                            <Table.Td>{row.asset_name_raw || row.asset_name_normalized || "—"}</Table.Td>
                            <Table.Td>{row.transaction_type_label ?? row.transaction_type}</Table.Td>
                            <Table.Td>{row.member}</Table.Td>
                            <Table.Td>{formatDate(row.filing_date)}</Table.Td>
                            <Table.Td>{formatDate(row.transaction_date)}</Table.Td>
                          </Table.Tr>
                        ))}
                      </Table.Tbody>
                    </Table>
                  </Table.ScrollContainer>
                </Stack>

                {totalPages > 1 ? (
                  <Group justify="space-between">
                    <Text size="sm" c="dimmed">
                      {data.total.toLocaleString()} rows · page {page} of {totalPages}
                    </Text>
                    <Pagination
                      total={totalPages}
                      value={page}
                      onChange={(p) => {
                        const next = new URLSearchParams(searchParams);
                        next.set("page", String(p));
                        setSearchParams(next);
                      }}
                      data-testid="review-pagination"
                    />
                  </Group>
                ) : null}
              </Stack>
            )}
          </ChartCard>
        </Stack>
      ) : null}
    </PageState>
  );
}
