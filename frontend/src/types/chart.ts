export type ChartTimeframe = "1D" | "1W" | "1M" | "3M" | "6M" | "1Y" | "5Y";

export const CHART_TIMEFRAMES: ChartTimeframe[] = [
  "1D",
  "1W",
  "1M",
  "3M",
  "6M",
  "1Y",
  "5Y",
];

export interface OhlcBar {
  time: string | number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number | null;
}

export interface ChartResponse {
  symbol: string;
  timeframe: ChartTimeframe;
  interval: string;
  tv_interval: string;
  bars: OhlcBar[];
}
