export type Theme = "light" | "dark";

export interface StockSignal {
  symbol: string;
  price: number;
  change_5d_pct: number | null;
  change_20d_pct: number | null;
  rsi: number | null;
  macd: number | null;
  macd_signal: number | null;
  macd_histogram: number | null;
  sma_20: number | null;
  sma_50: number | null;
  score: number;
  overall_score: number | null;
  signals: string[];
  warnings: string[];
  trend: string;
}

export interface WidgetConfig {
  id?: number;
  widget_type: string;
  size: "sm" | "md" | "lg";
  position: number;
  config: Record<string, unknown>;
}

export interface ScanResponse {
  scanned_at: string;
  index: string;
  index_label: string;
  total_scanned: number;
  total_matched: number;
  min_score: number;
  results: StockSignal[];
}

export interface IndexOption {
  id: string;
  label: string;
  description: string;
  slow_scan: boolean;
}

export interface IndicesResponse {
  indices: IndexOption[];
}

export interface IpoListing {
  symbol: string;
  company_name: string;
  security_type: string;
  ipo_start_date: string;
  ipo_end_date: string;
  listing_date: string;
  listing_date_display: string;
  issue_price: number | null;
  price_range: string;
  yf_symbol: string | null;
  listing_open: number | null;
  listing_close: number | null;
  listing_high: number | null;
  current_price: number | null;
  listing_day_gain_pct: number | null;
  gain_vs_issue_pct: number | null;
  gain_vs_listing_close_pct: number | null;
  gain_listing_open_to_current_pct: number | null;
  status: string;
}

export interface IpoTrackResponse {
  scanned_at: string;
  months: number;
  total_listed: number;
  with_market_data: number;
  results: IpoListing[];
}

export type AppTab = "screener" | "ipo";

export type {
  FinancialPeriod,
  SelectedStock,
  ShareholdingPeriod,
  StockInsightsResponse,
} from "./types/insights";
