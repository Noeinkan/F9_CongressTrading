export type PeriodParams = {
  lookback?: number | null;
  quarters?: string;
};

export type SessionResponse = {
  authenticated: boolean;
  auth_required: boolean;
  user: string | null;
};

export type LoginResponse = {
  user: string;
  auth_required: boolean;
};

export type SparklinePoint = {
  month: string | null;
  value: number;
};

export type KpiDelta = {
  value: number;
  percent: boolean;
  label: string;
};

export type HomeHero = {
  transaction_source: string;
  review_source: string;
  total_transactions: number;
  total_members: number;
  tracked_tickers: number;
  open_reviews: number;
  avg_confidence: number;
  avg_confidence_label: string;
  active_chambers: string;
  amount_low_total: number;
  amount_high_total: number;
  disclosed_range: string;
  coverage_from: string | null;
  coverage_to: string | null;
  latest_filing: string | null;
};

export type HomeKpi = {
  key: string;
  label: string;
  value: number | string;
  detail: string;
  sparkline: SparklinePoint[];
  delta: KpiDelta | null;
};

export type HomeTransactionRow = {
  member: string;
  chamber: string;
  party: string;
  ticker: string;
  issuer_name?: string;
  transaction_type_label: string;
  transaction_date: string | null;
  amount_range_raw: string;
  filing_date: string | null;
  disclosure_url: string;
};

export type HomeRankRow = {
  member?: string;
  ticker?: string;
  transactions: number;
  amount_low: number;
  amount_high: number;
  disclosed_range: string;
};

export type NetTradeRow = {
  ticker: string;
  first_trade: string | null;
  last_trade: string | null;
  direction: string;
  net_amount: number;
  net_label: string;
  buy_label: string;
  sell_label: string;
  trades: number;
};

export type TickerTimelineRow = {
  member: string;
  ticker?: string;
  transaction_date: string;
  transaction_type: string;
  txn_type_label?: string;
  transaction_type_label?: string;
  amount_low: number | null;
  amount_high: number | null;
  amount_range_raw?: string;
  issuer_name?: string;
  chamber?: string;
  owner_type?: string;
};

export type Ticker3DRow = {
  date: string;
  member: string;
  amount_high: number | null;
  transaction_type: string;
  txn_type_label: string;
  z: number;
};

export type TickerCumulativeRow = {
  member: string;
  date: string;
  cumulative_net: number;
  cumulative_label: string;
  txn_type_label: string;
};

export type TickerDrilldownResponse = {
  ready: boolean;
  ticker: string;
  ticker_timeline: TickerTimelineRow[];
  ticker_3d: Ticker3DRow[];
  ticker_cumulative: TickerCumulativeRow[];
};

export type HealthResponse = {
  status: string;
  auth_required: boolean;
  polygon_cache_rows: number;
};

export type HomeSummaryResponse = {
  ready: boolean;
  hero: HomeHero;
  kpis: HomeKpi[];
  latest_transactions: HomeTransactionRow[];
  breakdown: {
    by_chamber: { chamber: string; transactions: number }[];
    by_type: { transaction_type_label: string; transactions: number }[];
  };
  monthly_activity: {
    month: string | null;
    transactions: number;
    amount_low: number;
    amount_high: number;
  }[];
  top_members: HomeRankRow[];
  top_tickers: HomeRankRow[];
  members_leaderboard: MembersLeaderboardRow[];
  net_trade_amounts: NetTradeRow[];
  tickers_available: string[];
};

export type ColumnMeta = {
  key: string;
  label: string;
  type: "text" | "date" | "currency" | "number";
  sortable: boolean;
};

export type SortMeta = {
  column: string;
  order: string;
};

export type RawParams = PeriodParams & {
  search?: string;
  member?: string;
  chamber?: string;
  party?: string;
  ticker?: string;
  transaction_type?: string;
  date_from?: string;
  date_to?: string;
  amount_min?: number;
  amount_max?: number;
  sort?: string;
  order?: "asc" | "desc";
  page?: number;
  page_size?: number;
};

export type RawTransactionsResponse = {
  ready: boolean;
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  sort: SortMeta;
  rows: Record<string, unknown>[];
  columns: ColumnMeta[];
  source: string;
};

export type ReviewRow = {
  reason: string;
  status: string;
  notes?: string;
  member: string;
  chamber?: string;
  filing_type?: string;
  filing_date?: string | null;
  transaction_date?: string | null;
  asset_name_raw?: string;
  asset_name_normalized?: string;
  asset_type?: string;
  ticker: string;
  transaction_type_label?: string;
  transaction_type?: string;
  amount_range_raw: string;
  confidence_score?: number;
  review_status?: string;
  raw_document_path?: string;
  source_page?: number;
  source_row?: number;
};

export type ReviewSummaryResponse = {
  ready: boolean;
  review_source: string;
  kpis: {
    open_count: number;
    total_count: number;
    high_confidence_pct: number;
    high_confidence_label: string;
    by_reason: { reason: string; records: number }[];
    by_status: { status: string; records: number }[];
    by_month: { month: string | null; records: number }[];
  };
  rows: ReviewRow[];
  total: number;
  limit: number;
  offset: number;
};

export type PatternsCommitteeRow = {
  member: string;
  chamber: string;
  party: string;
  total_trades: number;
  relevant_trades: number;
  relevance_pct: number;
  top_committee: string;
  top_sector: string;
};

export type PatternsCoordinatedRow = {
  ticker: string;
  pattern: string;
  members: number;
  member_names: string;
  trades: number;
  date_from: string | null;
  date_to: string | null;
};

export type PatternsCallPutMonthlyRow = {
  month: string | null;
  option_side: string;
  transactions: number;
};

export type PatternsCallPutRatioRow = {
  month: string | null;
  call: number;
  put: number;
  call_put_ratio: number;
};

export type PatternsVolumeRow = {
  ticker: string;
  recent_disclosures: number;
  recent_per_month: number;
  prior_per_month: number;
  spike_ratio: number;
};

export type PatternsBipartisanRow = {
  ticker: string;
  members: number;
  democrat_trades: number;
  republican_trades: number;
  member_names: string;
  date_from: string | null;
  date_to: string | null;
};

export type PatternsCommitteeDrillRow = {
  ticker: string;
  sector: string;
  matching_committees: string;
  transaction_type_label: string;
  transaction_date: string | null;
  amount_range_raw: string;
};

export type PatternsCoordinatedTxRow = {
  member: string;
  ticker: string;
  transaction_type_label: string;
  transaction_date: string | null;
  filing_date?: string | null;
  amount_range_raw: string;
  chamber?: string;
  party?: string;
};

export type PatternsSummaryResponse = {
  ready: boolean;
  window_days: number;
  min_members: number;
  coordinated_limit: number;
  committee: {
    summary: PatternsCommitteeRow[];
    members_with_overlap: string[];
    coverage: {
      member_coverage_pct: number;
      sector_coverage_pct: number;
      members_mapped: number;
    };
  };
  coordinated: PatternsCoordinatedRow[];
  call_put: {
    monthly: PatternsCallPutMonthlyRow[];
    ratio: PatternsCallPutRatioRow[];
  };
  volume_anomalies: PatternsVolumeRow[];
  bipartisan: PatternsBipartisanRow[];
};

export type MembersLeaderboardRow = {
  member: string;
  trades: number;
  tickers: number;
  amount_low: number;
  amount_high: number;
  disclosed_range?: string;
  chamber: string;
  party: string;
  state: string;
};

export type MemberKpis = {
  member: string;
  trades: number;
  tickers: number;
  amount_low_total: number;
  amount_high_total: number;
  disclosed_range: string;
  chamber: string;
  party: string;
  state: string;
  sparklines: {
    transactions: SparklinePoint[];
    tickers: SparklinePoint[];
    disclosed_amount_high: SparklinePoint[];
  };
};

export type MemberTickerRow = {
  ticker: string;
  issuer_name?: string;
  transaction_type: string;
  transaction_type_label: string;
  transaction_date: string | null;
  filing_date?: string | null;
  amount_low: number | null;
  amount_high: number | null;
  amount_range_raw: string;
  disclosure_url?: string;
  price_trade?: string | null;
  price_session?: string | null;
  price_asof?: string | null;
  price_asof_session?: string | null;
  return_pct?: number | null;
  est_pnl_usd?: number | null;
  is_non_equity?: boolean;
};

export type MemberTickersResponse = {
  member: string;
  kpis: MemberKpis;
  rows: MemberTickerRow[];
};

export type MemberCommitteeRow = {
  ticker: string;
  sector: string;
  matching_committees: string;
  transaction_type_label: string;
  transaction_date: string | null;
  amount_range_raw: string;
};

export type MemberCommitteeResponse = {
  member: string;
  assignments_loaded: boolean;
  rows: MemberCommitteeRow[];
};

export type MemberActivityRow = {
  ticker: string;
  transaction_date: string;
  transaction_type: string;
  transaction_type_label: string;
  amount_range_raw: string;
  issuer_name?: string;
};

export type MemberActivityTimelineResponse = {
  member: string;
  truncated: boolean;
  truncate_note: string;
  tickers: string[];
  rows: MemberActivityRow[];
};

export type MembersSummaryResponse = {
  ready: boolean;
  transaction_source: string;
  leaderboard: MembersLeaderboardRow[];
  kpi_sparklines: {
    members: SparklinePoint[];
    tickers: SparklinePoint[];
    transactions: SparklinePoint[];
  };
};

export type TickersLeaderboardRow = {
  ticker: string;
  issuer_name: string;
  sector: string;
  trades: number;
  members: number;
  buy: number;
  sell: number;
  call: number;
  put: number;
  exchange: number;
  amount_low: number;
  amount_high: number;
  disclosed_range: string;
  first_trade: string | null;
  last_trade: string | null;
  return_pct: number | null;
  return_trade_count: number;
  is_non_equity?: boolean;
};

export type TickersListResponse = {
  ready: boolean;
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  sort: SortMeta;
  search: string;
  rows: TickersLeaderboardRow[];
  source: string;
};

export type TickerIssuer = {
  issuer_name: string;
  ticker: string;
  sector: string;
  industry: string;
  asset_type: string;
  resolution_status?: string;
  match_source?: string;
};

export type TickerProfileKpis = {
  ticker: string;
  trades: number;
  members: number;
  buy: number;
  sell: number;
  call: number;
  put: number;
  exchange: number;
  amount_low_total: number;
  amount_high_total: number;
  disclosed_range: string;
  first_trade: string | null;
  last_trade: string | null;
  return_pct: number | null;
  return_trade_count: number;
  sparklines?: {
    transactions: SparklinePoint[];
    members: SparklinePoint[];
    disclosed_amount_high: SparklinePoint[];
  };
};

export type TickerMemberRow = {
  member: string;
  chamber: string;
  party: string;
  buy: number;
  sell: number;
  call: number;
  put: number;
  exchange: number;
  trades: number;
  amount_low_sum: number;
  amount_high_sum: number;
  disclosed_range: string;
  first_trade: string | null;
  last_trade: string | null;
};

export type TickerTransactionRow = {
  member: string;
  chamber: string;
  party: string;
  ticker: string;
  transaction_type_label: string;
  transaction_type: string;
  transaction_date: string | null;
  filing_date: string | null;
  amount_low: number | null;
  amount_high: number | null;
  amount_range_raw: string;
  issuer_name: string;
  asset_name_raw?: string;
  disclosure_url?: string;
  price_trade?: string | null;
  price_session?: string | null;
  price_asof?: string | null;
  price_asof_session?: string | null;
  return_pct?: number | null;
  est_pnl_usd?: number | null;
  is_non_equity?: boolean;
};

export type TickerDetailResponse = {
  ready: boolean;
  ticker: string;
  issuer: TickerIssuer;
  kpis: TickerProfileKpis;
  disclosed_range: string;
  members: TickerMemberRow[];
  transactions: TickerTransactionRow[];
  transactions_total: number;
  transactions_limit: number;
  source: string;
};

export type TickerPriceOverlayResponse = {
  ticker: string;
  ready: boolean;
  bars: { date: string; close: number }[];
  trades: {
    transaction_date: string;
    y: number | null;
    member: string;
    transaction_type: string;
    transaction_type_label: string;
  }[];
};

export type TickerMemberTimelineResponse = {
  ticker: string;
  members: string[];
  rows: TickerTimelineRow[];
};

export type TickerCumulativeExposureRow = {
  member: string;
  transaction_date: string;
  cumulative_net: number;
  cumulative_label: string;
  txn_type_label: string;
  amount_range_raw: string;
};

export type TickerCumulativeExposureResponse = {
  ticker: string;
  members: string[];
  truncated: boolean;
  rows: TickerCumulativeExposureRow[];
};

export type TickersListParams = PeriodParams & {
  sort?: string;
  order?: "asc" | "desc";
  search?: string;
  page?: number;
  page_size?: number;
};

export type ReviewParams = PeriodParams & {
  limit?: number;
  offset?: number;
};

export type PatternsParams = PeriodParams & {
  window_days?: number;
  min_members?: number;
  coordinated_limit?: number;
};
