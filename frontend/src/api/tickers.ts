import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "./client";
import { buildPeriodSearch, buildTickersSearch } from "./params";
import type {
  PeriodParams,
  TickerCumulativeExposureResponse,
  TickerDetailResponse,
  TickerMemberTimelineResponse,
  TickerPriceOverlayResponse,
  TickersListParams,
  TickersListResponse,
} from "./types";

export function useTickersList(params?: TickersListParams) {
  return useQuery({
    queryKey: ["tickers", "list", params ?? {}],
    queryFn: () => apiFetch<TickersListResponse>(`/api/tickers${buildTickersSearch(params)}`),
  });
}

export function useTickerProfile(ticker: string | null, params?: PeriodParams) {
  const normalized = ticker?.trim().toUpperCase() ?? "";
  return useQuery({
    queryKey: ["tickers", "profile", normalized, params ?? {}],
    queryFn: () =>
      apiFetch<TickerDetailResponse>(
        `/api/tickers/${encodeURIComponent(normalized)}${buildPeriodSearch(params)}`,
      ),
    enabled: normalized.length > 0,
  });
}

export function useTickerPriceOverlay(ticker: string | null, params?: PeriodParams) {
  const normalized = ticker?.trim().toUpperCase() ?? "";
  return useQuery({
    queryKey: ["tickers", "price_overlay", normalized, params ?? {}],
    queryFn: () =>
      apiFetch<TickerPriceOverlayResponse>(
        `/api/tickers/${encodeURIComponent(normalized)}/price_overlay${buildPeriodSearch(params)}`,
      ),
    enabled: normalized.length > 0,
  });
}

export function useTickerMemberTimeline(ticker: string | null, params?: PeriodParams) {
  const normalized = ticker?.trim().toUpperCase() ?? "";
  return useQuery({
    queryKey: ["tickers", "member_timeline", normalized, params ?? {}],
    queryFn: () =>
      apiFetch<TickerMemberTimelineResponse>(
        `/api/tickers/${encodeURIComponent(normalized)}/member_timeline${buildPeriodSearch(params)}`,
      ),
    enabled: normalized.length > 0,
  });
}

export function useTickerCumulativeExposure(ticker: string | null, params?: PeriodParams) {
  const normalized = ticker?.trim().toUpperCase() ?? "";
  return useQuery({
    queryKey: ["tickers", "cumulative_exposure", normalized, params ?? {}],
    queryFn: () =>
      apiFetch<TickerCumulativeExposureResponse>(
        `/api/tickers/${encodeURIComponent(normalized)}/cumulative_exposure${buildPeriodSearch(params)}`,
      ),
    enabled: normalized.length > 0,
  });
}
