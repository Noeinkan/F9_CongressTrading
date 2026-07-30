import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "./client";
import { buildReviewSearch } from "./params";
import type {
  ReviewMutationResponse,
  ReviewParams,
  ReviewSummaryResponse,
} from "./types";

export function useReviewSummary(params?: ReviewParams) {
  return useQuery({
    queryKey: ["review", "summary", params ?? {}],
    queryFn: () =>
      apiFetch<ReviewSummaryResponse>(`/api/review/summary${buildReviewSearch(params)}`),
  });
}

function invalidateReviewQueries(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: ["review"] });
  void queryClient.invalidateQueries({ queryKey: ["home"] });
}

export function useResolveReviewItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      transactionId,
      ticker,
      applyToAsset = false,
    }: {
      transactionId: number;
      ticker: string;
      applyToAsset?: boolean;
    }) =>
      apiFetch<ReviewMutationResponse>(`/api/review/items/${transactionId}/resolve`, {
        method: "POST",
        body: { ticker, apply_to_asset: applyToAsset },
      }),
    onSuccess: () => invalidateReviewQueries(queryClient),
  });
}

export function useAcceptReviewItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      transactionId,
      applyToAsset = false,
    }: {
      transactionId: number;
      applyToAsset?: boolean;
    }) =>
      apiFetch<ReviewMutationResponse>(`/api/review/items/${transactionId}/accept`, {
        method: "POST",
        body: { apply_to_asset: applyToAsset },
      }),
    onSuccess: () => invalidateReviewQueries(queryClient),
  });
}

export function useDismissReviewItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (transactionId: number) =>
      apiFetch<ReviewMutationResponse>(`/api/review/items/${transactionId}/dismiss`, {
        method: "POST",
      }),
    onSuccess: () => invalidateReviewQueries(queryClient),
  });
}
