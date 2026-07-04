import {
  Anchor,
  Badge,
  Button,
  Card,
  Group,
  MultiSelect,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Text,
  Title,
} from "@mantine/core";
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
} from "@tanstack/react-table";
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import {
  useExecutiveFilers,
  useExecutiveFilings,
  useExecutiveHoldings,
  useExecutiveTransactions,
} from "@/api/executive";
import type {
  ExecutiveFiling,
  ExecutiveFiler,
  ExecutiveTransactionRow,
} from "@/api/types";
import { ChartCard } from "@/components/ChartCard";
import { PageState } from "@/components/PageState";
import { SectionIntro } from "@/components/SectionIntro";
import { formatDate, formatNumber } from "@/utils/format";
import { classifyTransaction, directionColor } from "@/utils/transactions";

const LOOKBACK_OPTIONS = [
  { value: "1", label: "Last 1 year" },
  { value: "2", label: "Last 2 years" },
  { value: "all", label: "All time" },
];

const TRANSACTION_TYPE_OPTIONS = [
  { value: "Buy", label: "Buy" },
  { value: "Sell", label: "Sell" },
  { value: "Exchange", label: "Exchange" },
];

function lookbackValue(raw: string | null): number | null {
  if (raw == null || raw === "" || raw === "all") return null;
  const parsed = Number.parseInt(raw, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function reviewStatusColor(status: string | undefined): string {
  const s = (status ?? "").toLowerCase();
  if (s === "approved" || s === "verified" || s === "ok") return "teal";
  if (s === "rejected" || s === "failed") return "red";
  if (s === "pending" || s === "manual_review" || s === "manual review") return "yellow";
  return "gray";
}

export function Executive() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [selectedTypes, setSelectedTypes] = useState<string[]>([]);

  const lookbackRaw = searchParams.get("lookback") ?? "1";
  const filingDocId = searchParams.get("filing_doc_id") ?? "";
  const ownerType = searchParams.get("owner_type") ?? "";
  const transactionType =
    selectedTypes.length === 1 ? selectedTypes[0] ?? "" : "";

  const filersQuery = useExecutiveFilers();
  const filingsQuery = useExecutiveFilings();
  const holdingsQuery = useExecutiveHoldings();

  const transactionsParams = useMemo(
    () => ({
      lookback: lookbackValue(lookbackRaw),
      transaction_type: transactionType || undefined,
      owner_type: ownerType || undefined,
      filing_doc_id: filingDocId || undefined,
      page: 1,
      page_size: 200,
    }),
    [lookbackRaw, transactionType, ownerType, filingDocId],
  );
  const transactionsQuery = useExecutiveTransactions(transactionsParams);

  const filers = useMemo(() => filersQuery.data ?? [], [filersQuery.data]);
  const filings = useMemo(() => filingsQuery.data ?? [], [filingsQuery.data]);
  const transactions = transactionsQuery.data?.rows ?? [];
  const totalTransactions = transactionsQuery.data?.total ?? 0;

  const primaryFiler: ExecutiveFiler | undefined = filers[0];
  const latestFiling: ExecutiveFiling | undefined = filings[0];

  const filingOptions = useMemo(
    () =>
      filings.map((f) => ({
        value: f.doc_id,
        label: `${formatDate(f.filing_date)} · ${f.filing_type} (${f.transaction_count})`,
      })),
    [filings],
  );

  const columns = useMemo<ColumnDef<ExecutiveTransactionRow>[]>(
    () => [
      {
        id: "transaction_date",
        accessorKey: "transaction_date",
        header: "Date",
        cell: ({ getValue }) => formatDate(getValue()),
      },
      {
        id: "asset_name_raw",
        accessorKey: "asset_name_raw",
        header: "Asset",
        cell: ({ getValue }) => {
          const v = getValue();
          if (typeof v === "string" && v.trim()) return v;
          return <Text c="dimmed">—</Text>;
        },
      },
      {
        id: "transaction_type_label",
        accessorKey: "transaction_type_label",
        header: "Type",
        cell: ({ getValue }) => {
          const label = typeof getValue() === "string" ? (getValue() as string) : "";
          if (!label) return <Text c="dimmed">—</Text>;
          const color = directionColor(classifyTransaction(label));
          return (
            <Badge color={color} variant="light" size="sm">
              {label}
            </Badge>
          );
        },
      },
      {
        id: "owner_type",
        accessorKey: "owner_type",
        header: "Owner",
        cell: ({ getValue }) => {
          const v = getValue();
          if (typeof v === "string" && v.trim()) return v;
          return <Text c="dimmed">—</Text>;
        },
      },
      {
        id: "amount_range_raw",
        accessorKey: "amount_range_raw",
        header: "Amount",
        cell: ({ getValue }) => {
          const v = getValue();
          if (typeof v === "string" && v.trim()) return v;
          return <Text c="dimmed">—</Text>;
        },
      },
      {
        id: "ticker",
        accessorKey: "ticker",
        header: "Ticker",
        cell: ({ getValue }) => {
          const v = getValue();
          if (typeof v === "string" && v.trim()) {
            return <Badge variant="light" color="navy" size="sm">{v}</Badge>;
          }
          return <Text c="dimmed">—</Text>;
        },
      },
      {
        id: "review_status",
        accessorKey: "review_status",
        header: "Review",
        cell: ({ getValue }) => {
          const v = getValue();
          const status = typeof v === "string" ? v : "";
          if (!status) return <Text c="dimmed">—</Text>;
          return (
            <Badge variant="light" color={reviewStatusColor(status)} size="sm">
              {status}
            </Badge>
          );
        },
      },
      {
        id: "source",
        header: "Source",
        cell: ({ row }) => {
          const url = row.original.disclosure_url || row.original.source_url || "";
          if (!url) return <Text c="dimmed">—</Text>;
          return (
            <Anchor href={url} target="_blank" rel="noreferrer" size="sm">
              view
            </Anchor>
          );
        },
      },
    ],
    [],
  );

  const table = useReactTable({
    data: transactions,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(searchParams);
    if (value === "") next.delete(key);
    else next.set(key, value);
    setSearchParams(next);
  };

  const isLoading =
    filersQuery.isLoading || filingsQuery.isLoading || transactionsQuery.isLoading;
  const isError =
    filersQuery.isError || filingsQuery.isError || transactionsQuery.isError;

  const holdingsCount = holdingsQuery.data?.length ?? 0;

  // Treat the page as "no data" until filings load and we know whether the
  // backend has anything. If filers/filings are both empty arrays we render a
  // helpful empty state rather than a broken table.
  const hasLoaded = !filingsQuery.isLoading && !filersQuery.isLoading;
  const hasNoData =
    hasLoaded && filers.length === 0 && filings.length === 0;

  return (
    <PageState isLoading={isLoading} isError={isError}>
      <Stack gap="md" data-testid="executive-page">
        <SectionIntro
          kicker="Executive"
          title="U.S. President — OGE Form 278-T periodic transactions"
          copy="Public financial disclosures filed by the Executive Branch via OGE Form 278-T (periodic transactions) and Form 278e (asset holdings). Backed by the same normalized transactions table; the backend scopes this view to chamber=Executive."
        />

        {hasNoData ? (
          <Card withBorder radius="md" padding="lg" data-testid="executive-empty">
            <Stack gap="xs">
              <Title order={4}>No Executive filings ingested yet</Title>
              <Text c="dimmed" size="sm">
                Run the OGE downloader and ingest pipeline to populate this view:
              </Text>
              <Text size="sm" style={{ fontFamily: "var(--mantine-font-family-monospace)" }}>
                python -m src.main download-oge &amp;&amp; python -m src.main ingest-oge
              </Text>
            </Stack>
          </Card>
        ) : (
          <>
            <Card withBorder radius="md" padding="md" data-testid="executive-header">
              <SimpleGrid cols={{ base: 1, sm: 2, md: 4 }} spacing="md">
                <Stack gap={2}>
                  <Text size="xs" c="dimmed" tt="uppercase" fw={700}>
                    Filer
                  </Text>
                  <Text fw={700} size="lg">
                    {primaryFiler?.filer_name ?? "—"}
                  </Text>
                  <Text size="xs" c="dimmed">
                    {primaryFiler
                      ? `${primaryFiler.filing_count} filings · ${primaryFiler.transaction_count} transactions`
                      : "Awaiting data"}
                  </Text>
                </Stack>
                <Stack gap={2}>
                  <Text size="xs" c="dimmed" tt="uppercase" fw={700}>
                    Latest filing date
                  </Text>
                  <Text fw={600}>{formatDate(primaryFiler?.latest_filing_date ?? null)}</Text>
                </Stack>
                <Stack gap={2}>
                  <Text size="xs" c="dimmed" tt="uppercase" fw={700}>
                    Total transactions
                  </Text>
                  <Text fw={600}>{formatNumber(totalTransactions)}</Text>
                  <Text size="xs" c="dimmed">
                    Latest holdings: {holdingsCount}
                  </Text>
                </Stack>
                <Stack gap={4} justify="flex-start">
                  {latestFiling?.source_url ? (
                    <Button
                      component="a"
                      href={latestFiling.source_url}
                      target="_blank"
                      rel="noreferrer"
                      variant="light"
                      color="navy"
                      data-testid="executive-source-link"
                    >
                      View original OGE filing
                    </Button>
                  ) : (
                    <Text size="sm" c="dimmed">
                      No source URL on the latest filing.
                    </Text>
                  )}
                </Stack>
              </SimpleGrid>
            </Card>

            <ChartCard
              collapsible
              title="Filings"
              caption="Click a filing to filter the transactions table below by document ID."
              testId="executive-filings-card"
            >
              {filings.length === 0 ? (
                <Text c="dimmed" data-testid="executive-filings-empty">
                  No filings available yet.
                </Text>
              ) : (
                <Table.ScrollContainer minWidth={600}>
                  <Table striped highlightOnHover data-testid="executive-filings-table">
                    <Table.Thead>
                      <Table.Tr>
                        <Table.Th>Filed</Table.Th>
                        <Table.Th>Type</Table.Th>
                        <Table.Th>Transactions</Table.Th>
                        <Table.Th>Source</Table.Th>
                        <Table.Th aria-label="row actions" />
                      </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                      {filings.map((f) => {
                        const active = filingDocId === f.doc_id;
                        return (
                          <Table.Tr
                            key={f.doc_id}
                            data-testid="executive-filing-row"
                            onClick={() => setParam("filing_doc_id", active ? "" : f.doc_id)}
                            style={{ cursor: "pointer" }}
                          >
                            <Table.Td>{formatDate(f.filing_date)}</Table.Td>
                            <Table.Td>{f.filing_type || "—"}</Table.Td>
                            <Table.Td>{formatNumber(f.transaction_count)}</Table.Td>
                            <Table.Td>
                              {f.source_url ? (
                                <Anchor
                                  href={f.source_url}
                                  target="_blank"
                                  rel="noreferrer"
                                  size="sm"
                                  onClick={(e) => e.stopPropagation()}
                                >
                                  PDF
                                </Anchor>
                              ) : (
                                <Text c="dimmed" size="sm">
                                  —
                                </Text>
                              )}
                            </Table.Td>
                            <Table.Td>
                              {active ? (
                                <Badge variant="filled" color="navy" size="sm">
                                  active
                                </Badge>
                              ) : null}
                            </Table.Td>
                          </Table.Tr>
                        );
                      })}
                    </Table.Tbody>
                  </Table>
                </Table.ScrollContainer>
              )}
            </ChartCard>

            <Group justify="space-between" align="flex-end" wrap="wrap" gap="md">
              <Title order={4}>Transactions</Title>
              <Group gap="md" align="flex-end" wrap="wrap">
                <Select
                  label="Lookback"
                  data={LOOKBACK_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
                  value={lookbackRaw}
                  onChange={(v) => {
                    if (!v) return;
                    setParam("lookback", v === "all" ? "" : v);
                  }}
                  allowDeselect={false}
                  data-testid="executive-lookback"
                  w={160}
                />
                <MultiSelect
                  label="Transaction type"
                  placeholder="All"
                  data={TRANSACTION_TYPE_OPTIONS}
                  value={selectedTypes}
                  onChange={setSelectedTypes}
                  clearable
                  data-testid="executive-type-filter"
                  w={220}
                />
                <Select
                  label="Filing"
                  placeholder="All filings"
                  data={filingOptions}
                  value={filingDocId || null}
                  onChange={(v) => setParam("filing_doc_id", v ?? "")}
                  clearable
                  data-testid="executive-filing-filter"
                  w={240}
                />
                <Select
                  label="Owner"
                  placeholder="All"
                  data={[
                    { value: "filer", label: "Filer" },
                    { value: "spouse", label: "Spouse" },
                    { value: "dependent", label: "Dependent" },
                  ]}
                  value={ownerType || null}
                  onChange={(v) => setParam("owner_type", v ?? "")}
                  clearable
                  data-testid="executive-owner-filter"
                  w={160}
                />
              </Group>
            </Group>

            <ChartCard collapsible title="Periodic transactions" testId="executive-tx-card">
              <Table.ScrollContainer minWidth={1000}>
                <Table striped highlightOnHover data-testid="executive-tx-table">
                  <Table.Thead>
                    {table.getHeaderGroups().map((hg) => (
                      <Table.Tr key={hg.id}>
                        {hg.headers.map((header) => (
                          <Table.Th key={header.id} data-testid={`executive-col-${header.id}`}>
                            {flexRender(header.column.columnDef.header, header.getContext())}
                          </Table.Th>
                        ))}
                      </Table.Tr>
                    ))}
                  </Table.Thead>
                  <Table.Tbody>
                    {table.getRowModel().rows.length ? (
                      table.getRowModel().rows.map((row) => (
                        <Table.Tr key={row.id} data-testid="executive-tx-row">
                          {row.getVisibleCells().map((cell) => (
                            <Table.Td key={cell.id}>
                              {flexRender(cell.column.columnDef.cell, cell.getContext())}
                            </Table.Td>
                          ))}
                        </Table.Tr>
                      ))
                    ) : (
                      <Table.Tr>
                        <Table.Td colSpan={columns.length || 1}>
                          <Text c="dimmed" ta="center" py="md">
                            No transactions match the current filters.
                          </Text>
                        </Table.Td>
                      </Table.Tr>
                    )}
                  </Table.Tbody>
                </Table>
              </Table.ScrollContainer>
              <Text size="sm" c="dimmed" mt="sm" data-testid="executive-tx-total">
                {formatNumber(totalTransactions)} transactions
                {filingDocId ? " in selected filing" : ""}
              </Text>
            </ChartCard>
          </>
        )}
      </Stack>
    </PageState>
  );
}