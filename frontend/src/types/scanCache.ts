import type { BrStMatch } from "./brst";
import type { GoldenStockMatch } from "./golden";
import type { MultiYearMatch } from "./multiYear";
import type { WeeklyStockMatch } from "./weekly";

export interface ScanCacheResponse {
  scan_type: string;
  matches: BrStMatch[] | MultiYearMatch[] | GoldenStockMatch[] | WeeklyStockMatch[];
  filter: {
    min_market_cap_cr?: number | null;
    max_market_cap_cr?: number | null;
  };
  scanned: number;
  total: number;
  last_scanned_at: string | null;
}
