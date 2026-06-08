import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "./client";
import { buildPeriodSearch } from "./params";
import type {
  MemberActivityTimelineResponse,
  MemberCommitteeResponse,
  MemberTickersResponse,
  MembersSummaryResponse,
  PeriodParams,
} from "./types";

export function useMembersSummary(params?: PeriodParams) {
  return useQuery({
    queryKey: ["members", "summary", params ?? {}],
    queryFn: () =>
      apiFetch<MembersSummaryResponse>(`/api/members/summary${buildPeriodSearch(params)}`),
  });
}

export function useMemberTickers(member: string | null, params?: PeriodParams) {
  const normalized = member?.trim() ?? "";
  return useQuery({
    queryKey: ["members", "tickers", normalized, params ?? {}],
    queryFn: () =>
      apiFetch<MemberTickersResponse>(
        `/api/members/${encodeURIComponent(normalized)}/tickers${buildPeriodSearch(params)}`,
      ),
    enabled: normalized.length > 0,
  });
}

export function useMemberCommitteeRelevant(member: string | null, params?: PeriodParams) {
  const normalized = member?.trim() ?? "";
  return useQuery({
    queryKey: ["members", "committee_relevant", normalized, params ?? {}],
    queryFn: () =>
      apiFetch<MemberCommitteeResponse>(
        `/api/members/${encodeURIComponent(normalized)}/committee_relevant${buildPeriodSearch(params)}`,
      ),
    enabled: normalized.length > 0,
  });
}

export function useMemberActivityTimeline(member: string | null, params?: PeriodParams) {
  const normalized = member?.trim() ?? "";
  return useQuery({
    queryKey: ["members", "activity_timeline", normalized, params ?? {}],
    queryFn: () =>
      apiFetch<MemberActivityTimelineResponse>(
        `/api/members/${encodeURIComponent(normalized)}/activity_timeline${buildPeriodSearch(params)}`,
      ),
    enabled: normalized.length > 0,
  });
}
