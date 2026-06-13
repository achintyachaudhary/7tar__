export type LiveTradingMode = "off" | "market_off" | "analysis" | "live";

export interface LiveTradingState {
  enabled: boolean;
  mode: LiveTradingMode;
  analysis_override: boolean;
  /** Kill switch — no new entries; open trades still run. */
  entries_paused?: boolean;
  market_open: boolean;
  capital_per_trade: number;
  starting_capital: number;
  strategy: string;
  last_tick_at: string | null;
  last_data_at: string | null;
  note: string | null;
  updated_at: string | null;
  /** Portfolio summary (merged from get_state) */
  realized_pnl?: number;
  unrealized_pnl?: number;
  total_pnl?: number;
  total_pnl_pct?: number;
  portfolio_equity?: number;
  deployed?: number;
  holdings_invested?: number;
  holdings_current?: number;
  holdings_pnl?: number;
  holdings_pnl_pct?: number;
  today_pnl?: number;
  today_pnl_pct?: number;
  available_cash?: number;
  max_per_trade?: number;
  trade_budget?: number;
  open_positions?: number;
  max_positions?: number;
  preview_strategy?: string;
  strategy_key?: string;
}

export interface LiveTradeCandidate {
  id: number;
  symbol: string;
  source: string;
  company_name: string | null;
  resistance: number;
  last_price: number | null;
  target_price: number | null;
  stop_price: number | null;
  volume_ratio: number | null;
  volume_confirmed: boolean;
  rationale: string | null;
  status: "watching" | "armed" | "in_trade" | "closed" | "skipped";
  notified: boolean;
  added_at: string | null;
  updated_at: string | null;
  entry_point?: string;
  bullets?: string[];
}

export interface SyncPreviewItem {
  symbol: string;
  source: string;
  company_name: string;
  price: number | null;
  resistance: number;
  target_price: number;
  stop_price: number;
  entry_point: string;
  bullets: string[];
  is_candidate: boolean;
  selected: boolean;
}

export interface SyncPreviewSection {
  source: string;
  label: string;
  count: number;
  watchlist_count?: number;
  items: SyncPreviewItem[];
}

export interface SyncPreviewResponse {
  sections: SyncPreviewSection[];
  total: number;
  watchlist_count?: number;
}

export interface LiveTrade {
  id: number;
  symbol: string;
  source: string;
  company_name: string | null;
  strategy: string;
  entry_price: number;
  entry_time: string | null;
  candidate_added_at: string | null;
  resistance: number | null;
  target_price: number | null;
  stop_price: number | null;
  qty: number;
  notional: number;
  peak_price: number | null;
  trough_price: number | null;
  last_price: number | null;
  status: "open" | "closed";
  exit_price: number | null;
  exit_time: string | null;
  exit_reason: string | null;
  pnl_abs: number | null;
  pnl_pct: number | null;
  days_held: number | null;
  rationale: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface StrategyOpenTradeMark {
  symbol: string;
  qty: number;
  entry_price: number;
  last_price: number | null;
}

export interface StrategySummaryRow {
  key: string;
  label: string;
  executed: boolean;
  is_preview?: boolean;
  trades: number;
  wins: number;
  win_rate: number;
  avg_pct: number;
  total_pnl_abs: number;
  total_pct: number;
  total_invested?: number;
  /** Open-position marks — lets the UI re-value the row from live ticks. */
  open_trades?: StrategyOpenTradeMark[];
}

export interface StrategySummary {
  capital_per_trade: number;
  trade_count: number;
  preview_strategy?: string;
  strategies: StrategySummaryRow[];
}

export interface StrategyTradeResult {
  symbol: string;
  company_name: string | null;
  source: string;
  entry_price: number;
  entry_time: string | null;
  exit_time: string | null;
  exit_price: number;
  exit_reason: string;
  pnl_pct: number;
  pnl_abs: number;
  days_held: number;
  peak_price: number | null;
  trough_price: number | null;
  qty: number;
  notional: number;
  is_open: boolean;
}

export interface StrategyTradesResponse {
  strategy_key: string;
  strategy_label: string;
  capital_per_trade: number;
  trades: StrategyTradeResult[];
}

export interface IntradayTradeResult {
  symbol: string;
  company_name: string | null;
  entry_price: number;
  exit_price: number;
  exit_reason: string;
  exit_time: string | null;
  pnl_pct: number;
  pnl_abs: number;
  minutes_held: number;
  peak_price: number | null;
  trough_price: number | null;
  qty: number;
  notional: number;
  is_open: boolean;
}

export interface IntradayStrategyResult {
  key: string;
  label: string;
  executed: boolean;
  trades: number;
  wins: number;
  win_rate: number;
  avg_pct: number;
  total_pnl_abs: number;
  total_pct: number;
  per_trade: IntradayTradeResult[];
}

export interface IntradayBacktestResponse {
  data_source: string;
  capital_per_trade: number;
  symbols_tested: string[];
  symbols_count: number;
  errors: string[];
  strategies: IntradayStrategyResult[];
}
