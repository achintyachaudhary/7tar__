import type { OhlcBar } from "./chart";

export interface DarvasBox {
  top: number;
  bottom: number;
  range_pct: number;
  start_date: string;
  end_date: string;
}

export interface DarvasMatch {
  symbol: string;
  company_name: string;
  price: number;
  box_top: number;
  box_bottom: number;
  box_range_pct: number;
  breakout_pct: number;
  boxes: DarvasBox[];
  boxes_count: number;
  avg_volume?: number | null;
  recent_volume?: number | null;
  volume_ratio?: number | null;
  volume_confirmed?: boolean;
  volume_threshold?: number | null;
  bars?: OhlcBar[];
}
