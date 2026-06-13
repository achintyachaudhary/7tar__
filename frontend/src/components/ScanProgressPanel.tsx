import { formatISTFromDate } from "../lib/formatTime";

interface ScanProgressPanelProps {
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
  formatLastScanned?: (date: Date) => string;
  idleMessage?: string;
  alwaysShow?: boolean;
}

function formatEta(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return "—";
  if (seconds < 60) return `~${Math.round(seconds)}s remaining`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `~${m}m ${s}s remaining`;
}

export default function ScanProgressPanel({
  scanning,
  scanned,
  total,
  currentSymbol,
  progressPercent,
  matchCount = 0,
  skippedCount,
  startedAt,
  error,
  lastScannedAt,
  formatLastScanned,
  idleMessage = 'Click "Run Scan" to start',
  alwaysShow = false,
}: ScanProgressPanelProps) {
  if (!scanning && !error && !alwaysShow && !lastScannedAt) {
    return null;
  }

  const formatTime = formatLastScanned ?? formatISTFromDate;
  const skipped = skippedCount ?? Math.max(0, scanned - matchCount);
  const etaSec =
    scanning && startedAt && scanned > 0 && total > scanned
      ? ((Date.now() - startedAt) / 1000 / scanned) * (total - scanned)
      : null;

  return (
    <div className="scan-progress">
      <div className="scan-progress-text">
        {scanning ? (
          <span style={{ color: "var(--accent)" }}>
            ● {scanned === 0 && total > 0 ? "Preloading price data…" : "Scanning Stock Database…"}
          </span>
        ) : error ? (
          <span style={{ color: "var(--error)" }}>⚠ Scan Interrupted</span>
        ) : lastScannedAt ? (
          <span style={{ color: "var(--success)" }}>
            ✓ Last scanned: {formatTime(lastScannedAt)}
          </span>
        ) : (
          <span style={{ color: "var(--muted)" }}>{idleMessage}</span>
        )}
        {scanning && (
          <span style={{ color: "var(--muted)", marginLeft: "1rem" }}>
            <strong style={{ color: "var(--text)" }}>{scanned}</strong> / {total} stocks
            {matchCount > 0 && (
              <span style={{ marginLeft: "0.75rem", color: "var(--success)" }}>
                {matchCount} passed
              </span>
            )}
            {skipped > 0 && (
              <span style={{ marginLeft: "0.75rem" }}>{skipped} skipped</span>
            )}
          </span>
        )}
      </div>

      {(scanning || progressPercent > 0) && (
        <div className="scan-progress-bar-track">
          <div
            className="scan-progress-bar-fill"
            style={{ width: `${progressPercent}%` }}
          />
        </div>
      )}

      <div className="scan-meta">
        <div>
          {scanning && currentSymbol
            ? `Scanning: ${currentSymbol}`
            : error || (lastScannedAt ? "Scan complete" : idleMessage)}
        </div>
        <div>
          {scanning ? (
            <>
              {progressPercent}%
              {etaSec != null && ` · ${formatEta(etaSec)}`}
            </>
          ) : (
            `${progressPercent}%`
          )}
        </div>
      </div>

      {error && !scanning && (
        <div className="scan-progress-error">{error}</div>
      )}
    </div>
  );
}
