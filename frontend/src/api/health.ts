import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "./client";
import type { HealthResponse } from "./types";

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: () => apiFetch<HealthResponse>("/api/health"),
    staleTime: 60_000,
  });
}
