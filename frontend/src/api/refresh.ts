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
  phase_label: string;
  phase_index: number;
  phase_total: number;
  sub_progress: number;
  sub_done: number;
  sub_total: number;
  sub_unit: string;
  eta_seconds: number | null;
  step_started_at: string | null;
  log_tail: string[];
  log_lines: string[];
  result: Record<string, unknown>;
};

export const refreshStatusQueryKey = ["refresh", "status"] as const;

const REFRESH_EXPANDED_KEY = "refresh-log-expanded";

export function formatDuration(seconds: number | null): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return "—";
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  if (mins <= 0) return `${secs}s`;
  return `${mins}m ${secs}s`;
}

export function formatEta(seconds: number | null): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds <= 0) return "ETA —";
  return `ETA ~${formatDuration(Math.round(seconds))} left`;
}

export function readRefreshExpanded(startedAt: string | null): boolean {
  if (!startedAt || typeof sessionStorage === "undefined") return false;
  try {
    return sessionStorage.getItem(`${REFRESH_EXPANDED_KEY}:${startedAt}`) === "1";
  } catch {
    return false;
  }
}

export function writeRefreshExpanded(startedAt: string | null, expanded: boolean): void {
  if (!startedAt || typeof sessionStorage === "undefined") return;
  try {
    const key = `${REFRESH_EXPANDED_KEY}:${startedAt}`;
    if (expanded) sessionStorage.setItem(key, "1");
    else sessionStorage.removeItem(key);
  } catch {
    // ignore storage failures
  }
}

function emptyRefreshStatus(partial?: Partial<RefreshStatusResponse>): RefreshStatusResponse {
  return {
    status: "idle",
    started_at: null,
    finished_at: null,
    current_step: "",
    progress: 0,
    phase_label: "",
    phase_index: 0,
    phase_total: 5,
    sub_progress: 0,
    sub_done: 0,
    sub_total: 0,
    sub_unit: "",
    eta_seconds: null,
    step_started_at: null,
    log_tail: [],
    log_lines: [],
    result: {},
    ...partial,
  };
}

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
    mutationFn: () =>
      apiFetch<RefreshStatusResponse>("/api/admin/refresh-data", {
        method: "POST",
        body: { restart: true },
      }),
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: refreshStatusQueryKey });
      const previous = queryClient.getQueryData<RefreshStatusResponse>(refreshStatusQueryKey);
      const restartingWhileRunning = previous?.status === "running";

      // Drop every cached query so the next mount refetches immediately,
      // regardless of staleTime. Prevents the "clicked Refresh but the table
      // still shows April" window caused by stale cache surviving across
      // tab switches while the job runs.
      queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== "refresh" });

      if (restartingWhileRunning && previous) {
        queryClient.setQueryData(refreshStatusQueryKey, {
          ...previous,
          status: "running",
          finished_at: null,
          current_step: "starting",
          progress: 0,
          phase_label: "Restarting refresh",
          sub_progress: 0,
          sub_done: 0,
          sub_total: 0,
          sub_unit: "",
          eta_seconds: null,
        });
      } else {
        queryClient.setQueryData(
          refreshStatusQueryKey,
          emptyRefreshStatus({
            status: "running",
            started_at: new Date().toISOString(),
            current_step: "Queued",
            phase_label: "Queued",
          }),
        );
      }

      return { previous };
    },
    onSuccess: (data) => {
      queryClient.setQueryData(refreshStatusQueryKey, data);
      void queryClient.invalidateQueries();
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
