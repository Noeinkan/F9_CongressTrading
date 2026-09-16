import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "./client";
import type {
  DemoAccessConfirmResponse,
  DemoAccessLinkInfo,
  DemoAccessRequestResponse,
  DemoStatus,
} from "./types";

export const demoQueryKey = ["demo", "status"] as const;

/**
 * Whether this deployment is the public demo, and what to say about it.
 *
 * Answers on every deployment — `{ enabled: false }` when the demo is off —
 * so one frontend build serves both the private dashboard and the demo.
 *
 * Unlike the one-shot session probe, this can change under the visitor's feet:
 * signing in, signing out, and the 45-minute clock running out all move
 * `access.status`. So this refetches when the tab regains focus, and every
 * sign-in/out flow and every DEMO_* refusal explicitly invalidates it — see
 * `DemoWall`. No polling interval: nothing here needs a tick faster than
 * "the user did something or came back to the tab".
 */
export function useDemoStatus() {
  return useQuery({
    queryKey: demoQueryKey,
    queryFn: () => apiFetch<DemoStatus>("/api/demo/status"),
    retry: false,
    refetchOnWindowFocus: true,
  });
}

/** Step 1 of sign-in: request a 6-digit code (and a link) by email. 404s when the demo or its gate is off. */
export function useDemoAccessRequest() {
  return useMutation({
    mutationFn: (email: string) =>
      apiFetch<DemoAccessRequestResponse>("/api/demo/access/request", {
        method: "POST",
        body: { email },
      }),
  });
}

/** Step 2 of sign-in: redeem the emailed code. Sets the session cookie on success. */
export function useDemoAccessCode() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (params: { email: string; code: string }) =>
      apiFetch<DemoAccessConfirmResponse>("/api/demo/access/code", {
        method: "POST",
        body: params,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: demoQueryKey });
    },
  });
}

/**
 * `GET /api/demo/access/link?t=` — looks the token up without spending it.
 * Corporate mail scanners open links automatically, so this alone must never
 * sign the visitor in; only `useDemoAccessLinkConfirm`'s POST does that.
 */
export function useDemoAccessLinkInfo(token: string | null) {
  return useQuery({
    queryKey: ["demo", "access-link", token],
    queryFn: () =>
      apiFetch<DemoAccessLinkInfo>(`/api/demo/access/link?t=${encodeURIComponent(token ?? "")}`),
    enabled: Boolean(token),
    retry: false,
  });
}

/** The button click on `/access/verify`: spends the link and signs in. */
export function useDemoAccessLinkConfirm() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (token: string) =>
      apiFetch<DemoAccessConfirmResponse>("/api/demo/access/link", {
        method: "POST",
        body: { t: token },
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: demoQueryKey });
    },
  });
}

export function useDemoSignOut() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch<{ ok: boolean }>("/api/demo/access/signout", { method: "POST" }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: demoQueryKey });
    },
  });
}
