import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "./client";
import { buildReviewSearch } from "./params";
import type { ReviewParams, ReviewSummaryResponse } from "./types";

export function useReviewSummary(params?: ReviewParams) {
  return useQuery({
    queryKey: ["review", "summary", params ?? {}],
    queryFn: () =>
      apiFetch<ReviewSummaryResponse>(`/api/review/summary${buildReviewSearch(params)}`),
  });
}
