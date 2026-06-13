import type { OhlcBar } from "./chart";

export interface TestPoint {
  time: string;
  price: number;
}

export interface MultiYearMatch {
  symbol: string;
  company_name: string;
  price: number;
  highest_high: number;
  distance_pct: number;
  tests_count: number;
  test_points: TestPoint[];
  avg_volume?: number | null;
  recent_volume?: number | null;
  volume_ratio?: number | null;
  volume_confirmed?: boolean;
  volume_threshold?: number | null;
  bars?: OhlcBar[];
}
