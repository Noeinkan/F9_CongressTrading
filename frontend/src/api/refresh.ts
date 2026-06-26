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
  log_lines: string[];
  result: Record<string, unknown>;
};

export const refreshStatusQueryKey = ["refresh", "status"] as const;

export function useRefreshStatus() {
  return useQuery({
    queryKey: refreshStatusQueryKey,
    queryFn: () => apiFetch<RefreshStatusResponse>("/api/admin/refresh-data/status"),
    refetchInterval: (query) =>
      query.state.data?.status === "running" ? 1000 : false,
  });
}

export function useStartRefresh() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (
      variables: { overwrite?: boolean; force_extract?: boolean; skip_senate?: boolean } = {},
    ) =>
      apiFetch<RefreshStatusResponse>("/api/admin/refresh-data", {
        method: "POST",
        body: {
          restart: true,
          overwrite: Boolean(variables.overwrite),
          force_extract: Boolean(variables.force_extract),
          skip_senate: Boolean(variables.skip_senate),
        },
      }),
    onSuccess: (data) => {
      queryClient.setQueryData(refreshStatusQueryKey, data);
      void queryClient.invalidateQueries({ queryKey: refreshStatusQueryKey });
      if (data.status === "succeeded") {
        void queryClient.invalidateQueries();
      }
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
