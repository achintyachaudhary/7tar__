export interface VolSqueezeMatch {
  symbol: string;
  company_name: string;
  industry: string | null;
  market_cap_cr: number | null;
  price: number;
  range_days: number;
  range_high: number;
  range_low: number;
  range_pct: number;
  dist_from_range_high_pct: number;
  atr_ratio: number;
  volume_dryup_ratio: number | null;
  entry_price: number;
  target_price: number;
  stop_price: number;
  reward_risk: number | null;
}
