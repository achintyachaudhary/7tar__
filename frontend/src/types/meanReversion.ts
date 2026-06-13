export interface MeanReversionMatch {
  symbol: string;
  company_name: string;
  industry: string | null;
  market_cap_cr: number | null;
  price: number;
  rsi: number;
  sma_20: number;
  sma_200: number | null;
  atr: number;
  high_20d: number;
  pullback_pct: number;
  entry_price: number;
  target_price: number;
  stop_price: number;
  reward_risk: number;
  avg_volume?: number | null;
  recent_volume?: number | null;
  volume_ratio?: number | null;
}
