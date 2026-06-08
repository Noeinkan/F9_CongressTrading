import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "./client";
import { buildPeriodSearch } from "./params";
import type { PeriodParams, TickerDrilldownResponse } from "./types";

export function useTickerDrilldown(ticker: string | null, params?: PeriodParams) {
  const normalized = ticker?.trim().toUpperCase() ?? "";
  return useQuery({
    queryKey: ["home", "ticker_drilldown", normalized, params ?? {}],
    queryFn: () => {
      const period = buildPeriodSearch(params);
      const suffix = period ? `&${period.slice(1)}` : "";
      return apiFetch<TickerDrilldownResponse>(
        `/api/home/ticker_drilldown?ticker=${encodeURIComponent(normalized)}${suffix}`,
      );
    },
    enabled: normalized.length > 0,
  });
}
