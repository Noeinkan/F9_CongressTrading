import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "./client";
import { buildRawSearch } from "./params";
import type { RawParams, RawTransactionsResponse } from "./types";

export function useRawTransactions(params?: RawParams) {
  return useQuery({
    queryKey: ["raw", "transactions", params ?? {}],
    queryFn: () =>
      apiFetch<RawTransactionsResponse>(`/api/raw/transactions${buildRawSearch(params)}`),
  });
}

export function rawExportCsvUrl(params?: RawParams): string {
  return `/api/raw/export.csv${buildRawSearch(params)}`;
}
