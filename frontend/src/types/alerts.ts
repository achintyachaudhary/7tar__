export type AlertDirection = "above" | "below";

export interface PriceAlert {
  id: number;
  symbol: string;
  company_name: string | null;
  target_price: number;
  direction: AlertDirection;
  email: string | null;
  note: string | null;
  active: boolean;
  triggered_at: string | null;
  triggered_price: number | null;
  created_at: string;
  updated_at: string;
  /** Live quote — present on active alerts when market data is loaded. */
  ltp?: number | null;
  change_day_pct?: number | null;
  change_7d_pct?: number | null;
}
