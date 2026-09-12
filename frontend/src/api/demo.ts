import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { sessionQueryKey } from "./auth";
import { apiFetch } from "./client";
import type { DemoSessionResponse, DemoStatus } from "./types";

export const demoQueryKey = ["demo", "status"] as const;

/**
 * Whether this deployment is the public demo, and what to say about it.
 *
 * Answers on every deployment — `{ enabled: false }` when the demo is off —
 * so one frontend build serves both the private dashboard and the demo. Probed
 * once per app lifetime, like the session probe: the answer is a property of
 * the server process and cannot change while the tab is open.
 */
export function useDemoStatus() {
  return useQuery({
    queryKey: demoQueryKey,
    queryFn: () => apiFetch<DemoStatus>("/api/demo/status"),
    retry: false,
    staleTime: Infinity,
    gcTime: Infinity,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
  });
}

/** Sign the visitor in as the demo user. 404s when the demo is off. */
export function useDemoSignIn() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<DemoSessionResponse>("/api/demo/session", { method: "POST" }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: sessionQueryKey });
    },
  });
}
