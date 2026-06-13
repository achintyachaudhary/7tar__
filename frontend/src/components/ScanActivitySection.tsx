import ScanProgressPanel from "./ScanProgressPanel";
import ScanLogPanel from "./ScanLogPanel";
import type { ScanLogEntry } from "../types/scanLog";

interface ScanActivitySectionProps {
  scanning: boolean;
  scanned: number;
  total: number;
  currentSymbol?: string;
  progressPercent: number;
  matchCount?: number;
  skippedCount?: number;
  startedAt?: number;
  error?: string | null;
  lastScannedAt?: Date | null;
  logs?: ScanLogEntry[];
  alwaysShowProgress?: boolean;
  logTitle?: string;
}

export default function ScanActivitySection({
  scanning,
  scanned,
  total,
  currentSymbol,
  progressPercent,
  matchCount,
  skippedCount,
  startedAt,
  error,
  lastScannedAt,
  logs = [],
  alwaysShowProgress = true,
  logTitle = "Scan activity log",
}: ScanActivitySectionProps) {
  const showLogs = scanning || logs.length > 0;

  return (
    <div className="scan-activity-section">
      <ScanProgressPanel
        scanning={scanning}
        scanned={scanned}
        total={total}
        currentSymbol={currentSymbol}
        progressPercent={progressPercent}
        matchCount={matchCount}
        skippedCount={skippedCount}
        startedAt={startedAt}
        error={error}
        lastScannedAt={lastScannedAt}
        alwaysShow={alwaysShowProgress}
      />
      {showLogs && (
        <ScanLogPanel
          logs={logs}
          title={logTitle}
          maxHeight={scanning ? 280 : 360}
        />
      )}
    </div>
  );
}
