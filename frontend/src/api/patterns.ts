import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "./client";
import { buildPatternsSearch, buildPeriodSearch } from "./params";
import type {
  PatternsCoordinatedTxRow,
  PatternsParams,
  PatternsSummaryResponse,
  PeriodParams,
} from "./types";

export function usePatternsSummary(params?: PatternsParams) {
  return useQuery({
    queryKey: ["patterns", "summary", params ?? {}],
    queryFn: () =>
      apiFetch<PatternsSummaryResponse>(`/api/patterns/summary${buildPatternsSearch(params)}`),
  });
}

export function usePatternsCommitteeRelevant(member: string | null, params?: PeriodParams) {
  const normalized = member?.trim() ?? "";
  return useQuery({
    queryKey: ["patterns", "committee_relevant", normalized, params ?? {}],
    queryFn: () => {
      const period = buildPeriodSearch(params);
      const suffix = period ? `&${period.slice(1)}` : "";
      return apiFetch<{ member: string; assignments_loaded: boolean; rows: import("./types").PatternsCommitteeDrillRow[] }>(
        `/api/patterns/committee_relevant?member=${encodeURIComponent(normalized)}${suffix}`,
      );
    },
    enabled: normalized.length > 0,
  });
}

export type CoordinatedTxParams = PeriodParams & {
  ticker: string;
  pattern: string;
  window_days?: number;
  limit?: number;
};

export function usePatternsCoordinatedTransactions(params: CoordinatedTxParams | null) {
  const enabled = Boolean(params?.ticker && params?.pattern);
  return useQuery({
    queryKey: ["patterns", "coordinated_transactions", params ?? {}],
    queryFn: () => {
      if (!params) throw new Error("missing params");
      const search = new URLSearchParams({
        ticker: params.ticker,
        pattern: params.pattern,
      });
      if (params.window_days !== undefined) {
        search.set("window_days", String(params.window_days));
      }
      if (params.limit !== undefined) {
        search.set("limit", String(params.limit));
      }
      const period = buildPeriodSearch(params);
      const suffix = period ? `&${period.slice(1)}` : "";
      return apiFetch<{ rows: PatternsCoordinatedTxRow[] }>(
        `/api/patterns/coordinated_transactions?${search.toString()}${suffix}`,
      );
    },
    enabled,
  });
}
