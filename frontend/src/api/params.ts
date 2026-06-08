import type { PatternsParams, PeriodParams, RawParams, ReviewParams, TickersListParams } from "./types";

export function buildPeriodSearch(params?: PeriodParams): string {
  const search = new URLSearchParams();
  if (params?.lookback !== undefined && params.lookback !== null) {
    search.set("lookback", String(params.lookback));
  } else if (params?.lookback === null) {
    search.set("lookback", "0");
  }
  if (params?.quarters) {
    search.set("quarters", params.quarters);
  }
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

export function buildRawSearch(params?: RawParams): string {
  const search = new URLSearchParams();
  if (!params) {
    return "";
  }
  const lookbackValue = params.lookback === null ? 0 : params.lookback;
  const entries: [string, string | number | undefined][] = [
    ["lookback", lookbackValue],
    ["quarters", params.quarters],
    ["search", params.search],
    ["member", params.member],
    ["chamber", params.chamber],
    ["party", params.party],
    ["ticker", params.ticker],
    ["transaction_type", params.transaction_type],
    ["date_from", params.date_from],
    ["date_to", params.date_to],
    ["amount_min", params.amount_min],
    ["amount_max", params.amount_max],
    ["sort", params.sort],
    ["order", params.order],
    ["page", params.page],
    ["page_size", params.page_size],
  ];
  for (const [key, value] of entries) {
    if (value !== undefined && value !== "") {
      search.set(key, String(value));
    }
  }
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

export function buildTickersSearch(params?: TickersListParams): string {
  const search = new URLSearchParams();
  if (!params) {
    return "";
  }
  const lookbackValue = params.lookback === null ? 0 : params.lookback;
  const entries: [string, string | number | undefined][] = [
    ["lookback", lookbackValue],
    ["quarters", params.quarters],
    ["sort", params.sort],
    ["order", params.order],
    ["search", params.search],
    ["page", params.page],
    ["page_size", params.page_size],
  ];
  for (const [key, value] of entries) {
    if (value !== undefined && value !== "") {
      search.set(key, String(value));
    }
  }
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

export function buildReviewSearch(params?: ReviewParams): string {
  const search = new URLSearchParams();
  if (params?.lookback !== undefined && params.lookback !== null) {
    search.set("lookback", String(params.lookback));
  } else if (params?.lookback === null) {
    search.set("lookback", "0");
  }
  if (params?.quarters) {
    search.set("quarters", params.quarters);
  }
  if (params?.limit !== undefined) {
    search.set("limit", String(params.limit));
  }
  if (params?.offset !== undefined) {
    search.set("offset", String(params.offset));
  }
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

export function buildPatternsSearch(params?: PatternsParams): string {
  const search = new URLSearchParams();
  if (params?.lookback !== undefined && params.lookback !== null) {
    search.set("lookback", String(params.lookback));
  } else if (params?.lookback === null) {
    search.set("lookback", "0");
  }
  if (params?.quarters) {
    search.set("quarters", params.quarters);
  }
  if (params?.window_days !== undefined) {
    search.set("window_days", String(params.window_days));
  }
  if (params?.min_members !== undefined) {
    search.set("min_members", String(params.min_members));
  }
  if (params?.coordinated_limit !== undefined) {
    search.set("coordinated_limit", String(params.coordinated_limit));
  }
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}
