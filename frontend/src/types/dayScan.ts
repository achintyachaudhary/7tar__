export interface DayScanRow {
  symbol: string;
  company_name: string;
  industry: string | null;
  market_cap_cr: number | null;
  pe_ratio: number | null;
  roce_pct: number | null;
  return_1d_pct: number | null;
  return_1w_pct: number | null;
  return_1m_pct: number | null;
  return_1y_pct: number | null;
  last_price: number | null;
  prices_through_date: string | null;
  updated_at: string | null;
}

export interface DayScanListResponse {
  total: number;
  rows: DayScanRow[];
}

export interface DayScanStatus {
  running: boolean;
  total: number;
  processed: number;
  fetched: number;
  skipped: number;
  failed: number;
  current_symbol: string;
  started_at: string | null;
  completed_at: string | null;
  error: string | null;
}

export interface ListingFetchStatus extends DayScanStatus {
  listing_total: number;
  listing_completed: number;
  all_listing_done: boolean;
}

export interface DayScanSyncStatus {
  expected_through_date: string;
  sync_through_date: string | null;
  min_prices_through_date: string | null;
  snapshot_count: number;
  universe_count: number;
  needs_sync: boolean;
  last_sync_at: string | null;
  running: boolean;
}

export interface DbTableMeta {
  name: string;
  row_count: number;
}

export interface DbTableData {
  table: string;
  columns: string[];
  rows: Record<string, unknown>[];
  total: number;
  offset: number;
  limit: number;
}

export interface DayScanChartResponse {
  symbol: string;
  company_name: string;
  bar_count: number;
  from_date: string | null;
  to_date: string | null;
  bars: import("./chart").OhlcBar[];
}
