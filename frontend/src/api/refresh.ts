import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "./client";

export type RefreshJobStatus =
  | "idle"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled";

export type RefreshStatusResponse = {
  status: RefreshJobStatus;
  started_at: string | null;
  finished_at: string | null;
  current_step: string;
  progress: number;
  log_tail: string[];
  result: Record<string, unknown>;
};

export const refreshStatusQueryKey = ["refresh", "status"] as const;

export function useRefreshStatus() {
  return useQuery({
    queryKey: refreshStatusQueryKey,
    queryFn: () => apiFetch<RefreshStatusResponse>("/api/admin/refresh-data/status"),
    refetchInterval: (query) =>
      query.state.data?.status === "running" ? 2000 : false,
  });
}

export function useStartRefresh() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<RefreshStatusResponse>("/api/admin/refresh-data", {
        method: "POST",
        body: { restart: true },
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: refreshStatusQueryKey });
    },
  });
}

export function useCancelRefresh() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<RefreshStatusResponse>("/api/admin/refresh-data/cancel", {
        method: "POST",
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: refreshStatusQueryKey });
    },
  });
}
