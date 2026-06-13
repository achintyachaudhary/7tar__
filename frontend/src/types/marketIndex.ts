import type { OhlcBar } from "./chart";

export interface MarketIndexQuote {
  index_id: string;
  display_name: string;
  yf_symbol: string;
  last_value: number | null;
  change_abs: number | null;
  change_pct: number | null;
  updated_at: string | null;
}

export interface MarketIndicesResponse {
  indices: MarketIndexQuote[];
  market_open?: boolean;
  session_phase?: "pre_open" | "open" | "closed";
  as_of_label?: string | null;
}

export interface MarketIndexChartResponse {
  index_id: string;
  display_name: string;
  yf_symbol: string;
  timeframe: string;
  interval: string;
  bars: OhlcBar[];
}
