import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "./client";
import type { LoginResponse, SessionResponse } from "./types";

export const sessionQueryKey = ["session"] as const;

export function useSessionQuery() {
  return useQuery({
    queryKey: sessionQueryKey,
    queryFn: () => apiFetch<SessionResponse>("/api/session"),
    retry: false,
  });
}

/**
 * One-shot session probe used on cold load (Login screen, RequireAuth).
 * Sets `staleTime: Infinity` so we only ever probe once per app lifetime —
 * subsequent auth state changes flow through `useSessionQuery` / `useLogin`'s
 * `invalidateQueries`.
 */
export function useSessionProbe() {
  return useQuery({
    queryKey: sessionQueryKey,
    queryFn: () => apiFetch<SessionResponse>("/api/session"),
    retry: false,
    staleTime: Infinity,
    gcTime: Infinity,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
  });
}

export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (credentials: { username: string; password: string }) =>
      apiFetch<LoginResponse>("/api/login", {
        method: "POST",
        body: credentials,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: sessionQueryKey });
    },
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch<{ ok: boolean }>("/api/logout", { method: "POST" }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: sessionQueryKey });
    },
  });
}
