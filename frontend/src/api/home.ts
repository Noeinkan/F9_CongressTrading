import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "./client";
import { buildPeriodSearch } from "./params";
import type { HomeSummaryResponse, PeriodParams } from "./types";

export function useHomeSummary(params?: PeriodParams) {
  return useQuery({
    queryKey: ["home", "summary", params ?? {}],
    queryFn: () =>
      apiFetch<HomeSummaryResponse>(`/api/home/summary${buildPeriodSearch(params)}`),
  });
}

export function netTradeCsvUrl(params?: PeriodParams): string {
  return `/api/home/net_trade.csv${buildPeriodSearch(params)}`;
}
