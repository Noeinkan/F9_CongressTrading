import {
  Alert,
  Anchor,
  Button,
  Checkbox,
  Group,
  Pagination,
  Slider,
  Stack,
  Table,
  Text,
  TextInput,
} from "@mantine/core";
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type SortingState,
} from "@tanstack/react-table";
import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { useHealth } from "@/api/health";
import { rawExportCsvUrl, useRawTransactions } from "@/api/raw";
import type { ColumnMeta, RawParams } from "@/api/types";
import { ChartCard } from "@/components/ChartCard";
import { useFilters } from "@/components/FilterContext";
import { PageState } from "@/components/PageState";
import { SectionIntro } from "@/components/SectionIntro";
import { formatCurrency, formatDate, formatNumber } from "@/utils/format";

function quartersParam(quarters: string[]): string | undefined {
  if (quarters.length === 4) return undefined;
  return quarters.join(",");
}

function cellContent(col: ColumnMeta, value: unknown): React.ReactNode {
  if (value == null || value === "") return "—";
  switch (col.type) {
    case "date":
      return formatDate(value);
    case "currency":
      return formatCurrency(value);
    case "number":
      return formatNumber(value);
    default:
      if (col.key === "ticker" && typeof value === "string" && value) {
        return (
          <Anchor component={Link} to={`/tickers?ticker=${encodeURIComponent(value)}`} size="sm">
            {value}
          </Anchor>
        );
      }
      if (col.key === "disclosure_url" && typeof value === "string" && value) {
        return (
          <Anchor href={value} target="_blank" rel="noreferrer" size="sm">
            PDF
          </Anchor>
        );
      }
      return String(value);
  }
}

export function Raw() {
  const { lookback, quarters } = useFilters();
  const [searchParams, setSearchParams] = useSearchParams();
  const [polygonEstimates, setPolygonEstimates] = useState(false);
  const [searchDraft, setSearchDraft] = useState(searchParams.get("search") ?? "");
  const search = searchParams.get("search") ?? "";

  const page = Number(searchParams.get("page") ?? "1") || 1;
  const pageSize = Number(searchParams.get("page_size") ?? "50") || 50;
  const sortColumn = searchParams.get("sort") ?? "transaction_date";
  const sortOrder = (searchParams.get("order") ?? "desc") as "asc" | "desc";

  const periodParams = useMemo(
    () => ({
      lookback,
      quarters: quartersParam(quarters),
    }),
    [lookback, quarters],
  );

  const rawParams: RawParams = useMemo(
    () => ({
      ...periodParams,
      search: search || undefined,
      sort: sortColumn,
      order: sortOrder,
      page,
      page_size: pageSize,
    }),
    [periodParams, search, sortColumn, sortOrder, page, pageSize],
  );

  const { data, isLoading, isError } = useRawTransactions(rawParams);
  const health = useHealth();

  const sorting: SortingState = [{ id: sortColumn, desc: sortOrder === "desc" }];

  const columns = useMemo(
    () =>
      (data?.columns ?? []).map((col) => ({
        id: col.key,
        accessorKey: col.key,
        header: col.label,
        enableSorting: col.sortable,
        meta: col,
      })),
    [data?.columns],
  );

  const table = useReactTable({
    data: data?.rows ?? [],
    columns,
    state: { sorting },
    manualSorting: true,
    manualPagination: true,
    getCoreRowModel: getCoreRowModel(),
    pageCount: data?.total_pages ?? 0,
  });

  const updateParams = (patch: Record<string, string | number>) => {
    const next = new URLSearchParams(searchParams);
    for (const [key, value] of Object.entries(patch)) {
      if (value === "" && key === "search") next.delete("search");
      else next.set(key, String(value));
    }
    setSearchParams(next);
  };

  const showPolygonAlert =
    polygonEstimates && (health.data?.polygon_cache_rows ?? 0) === 0;

  return (
    <PageState isLoading={isLoading} isError={isError} ready={data?.ready ?? false}>
      <Stack gap="md" data-testid="raw-page">
        <SectionIntro
          kicker="Raw Data"
          title="Filtered normalized dataset"
          copy="Server-side sort, filter, and pagination over the active period slice. Export the full filtered set as CSV."
        />

        <Group justify="space-between" align="flex-end" wrap="wrap" gap="md">
          <Group gap="md" align="flex-end" wrap="wrap">
            <TextInput
              label="Search"
              placeholder="Member, ticker, issuer…"
              value={searchDraft}
              onChange={(e) => setSearchDraft(e.currentTarget.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") updateParams({ search: searchDraft, page: 1 });
              }}
              data-testid="raw-search"
            />
            <Checkbox
              label="Polygon return estimates"
              checked={polygonEstimates}
              onChange={(e) => setPolygonEstimates(e.currentTarget.checked)}
              data-testid="raw-polygon-toggle"
            />
            <div style={{ minWidth: 200 }}>
              <Text size="sm" fw={500} mb={4}>
                Rows per page: {pageSize}
              </Text>
              <Slider
                min={10}
                max={200}
                step={10}
                value={pageSize}
                onChange={(v) => updateParams({ page_size: v, page: 1 })}
                data-testid="raw-page-size"
              />
            </div>
          </Group>
          <Button
            component="a"
            href={rawExportCsvUrl(rawParams)}
            download
            variant="light"
            data-testid="raw-download"
          >
            Download CSV
          </Button>
        </Group>

        {showPolygonAlert ? (
          <Alert color="orange" variant="light" data-testid="raw-polygon-alert">
            Polygon daily bar cache is empty. Warm it with{" "}
            <code>python -m src.main warm-polygon-price-cache</code> before enabling return
            estimates.
          </Alert>
        ) : null}

        <ChartCard title="Transactions" testId="raw-table-card">
          <Table.ScrollContainer minWidth={900}>
            <Table striped highlightOnHover data-testid="raw-table">
              <Table.Thead>
                {table.getHeaderGroups().map((hg) => (
                  <Table.Tr key={hg.id}>
                    {hg.headers.map((header) => {
                      const col = header.column.columnDef.meta as ColumnMeta | undefined;
                      return (
                        <Table.Th
                          key={header.id}
                          style={{ cursor: col?.sortable ? "pointer" : "default" }}
                          onClick={() => {
                            if (!col?.sortable) return;
                            const nextOrder =
                              sortColumn === col.key && sortOrder === "desc" ? "asc" : "desc";
                            updateParams({ sort: col.key, order: nextOrder, page: 1 });
                          }}
                          data-testid={`raw-sort-${header.id}`}
                        >
                          {flexRender(header.column.columnDef.header, header.getContext())}
                          {sortColumn === header.id ? (sortOrder === "desc" ? " ↓" : " ↑") : ""}
                        </Table.Th>
                      );
                    })}
                  </Table.Tr>
                ))}
              </Table.Thead>
              <Table.Tbody>
                {table.getRowModel().rows.length ? (
                  table.getRowModel().rows.map((row) => (
                    <Table.Tr key={row.id} data-testid="raw-row">
                      {row.getVisibleCells().map((cell) => {
                        const col = cell.column.columnDef.meta as ColumnMeta;
                        return (
                          <Table.Td key={cell.id}>
                            {cellContent(col, cell.getValue())}
                          </Table.Td>
                        );
                      })}
                    </Table.Tr>
                  ))
                ) : (
                  <Table.Tr>
                    <Table.Td colSpan={columns.length || 1}>
                      <Text c="dimmed" ta="center" py="md">
                        No rows match the current filters.
                      </Text>
                    </Table.Td>
                  </Table.Tr>
                )}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
          {data && data.total_pages > 0 ? (
            <Group justify="space-between" mt="md">
              <Text size="sm" c="dimmed">
                {data.total.toLocaleString()} rows · page {data.page} of {data.total_pages}
              </Text>
              <Pagination
                total={data.total_pages}
                value={data.page}
                onChange={(p) => updateParams({ page: p })}
                data-testid="raw-pagination"
              />
            </Group>
          ) : null}
        </ChartCard>
      </Stack>
    </PageState>
  );
}
