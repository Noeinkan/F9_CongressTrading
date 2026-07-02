import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "./client";
import type {
  ExecutiveFiler,
  ExecutiveFiling,
  ExecutiveHolding,
  ExecutiveTransactionsParams,
  ExecutiveTransactionsResponse,
} from "./types";

function buildExecutiveSearch(params?: ExecutiveTransactionsParams): string {
  const search = new URLSearchParams();
  if (!params) return "";
  const lookbackValue = params.lookback === null ? 0 : params.lookback;
  const entries: [string, string | number | undefined][] = [
    ["lookback", lookbackValue],
    ["quarters", params.quarters],
    ["transaction_type", params.transaction_type],
    ["owner_type", params.owner_type],
    ["filing_doc_id", params.filing_doc_id],
    ["page", params.page],
    ["page_size", params.page_size],
  ];
  for (const [key, value] of entries) {
    if (value !== undefined && value !== "") {
      search.set(key, String(value));
    }
  }
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

export function useExecutiveFilers() {
  return useQuery({
    queryKey: ["executive", "filers"],
    queryFn: () =>
      apiFetch<{ ready: boolean; filers: ExecutiveFiler[] }>(
        "/api/executive/filers",
      ),
    select: (resp) => resp.filers,
  });
}

export function useExecutiveFilings() {
  return useQuery({
    queryKey: ["executive", "filings"],
    queryFn: () =>
      apiFetch<{ ready: boolean; filings: ExecutiveFiling[] }>(
        "/api/executive/filings",
      ),
    select: (resp) => resp.filings,
  });
}

export function useExecutiveHoldings() {
  return useQuery({
    queryKey: ["executive", "holdings"],
    queryFn: () =>
      apiFetch<{ ready: boolean; holdings: ExecutiveHolding[] }>(
        "/api/executive/holdings",
      ),
    select: (resp) => resp.holdings,
  });
}

export function useExecutiveTransactions(params?: ExecutiveTransactionsParams) {
  return useQuery({
    queryKey: ["executive", "transactions", params ?? {}],
    queryFn: () =>
      apiFetch<ExecutiveTransactionsResponse>(
        `/api/executive/transactions${buildExecutiveSearch(params)}`,
      ),
  });
}
