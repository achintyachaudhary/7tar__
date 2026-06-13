export interface VolumeSurgeMatch {
  symbol: string;
  company_name: string;
  industry: string | null;
  market_cap_cr: number | null;
  price: number;
  day_change_pct: number;
  volume_multiple: number;
  day_volume: number;
  avg_volume_50d: number;
  close_strength_pct: number;
  surge_high: number;
  surge_low: number;
  entry_price: number;
  stop_price: number;
}
