export type ScanLogOutcome = "match" | "skip" | "error" | "info";

export interface ScanLogEntry {
  ts: string;
  symbol: string;
  outcome: ScanLogOutcome;
  message: string;
  scanned: number;
  total: number;
  match_count: number;
}

export interface ActiveScanState {
  scanType: string;
  scanning: boolean;
  scanned: number;
  total: number;
  currentSymbol: string;
  matchCount: number;
  skippedCount: number;
  logs: ScanLogEntry[];
  startedAt: number;
  historyId?: number | null;
}
