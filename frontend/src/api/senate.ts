import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "./client";
import { buildPeriodSearch } from "./params";
import type { PeriodParams, SenateSummaryResponse } from "./types";

export function useSenateSummary(params?: PeriodParams) {
  return useQuery({
    queryKey: ["senate", "summary", params ?? {}],
    queryFn: () =>
      apiFetch<SenateSummaryResponse>(`/api/senate/summary${buildPeriodSearch(params)}`),
  });
}
