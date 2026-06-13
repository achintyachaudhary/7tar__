import { useEffect, useMemo, useState } from "react";
import { useGlobalScanMonitor } from "../context/GlobalScanMonitorContext";

const SCAN_LABELS: Record<string, string> = {
  brst: "Year Breakout",
  multi_year: "Multi-Year Breakout",
  golden: "Golden Stocks",
  weekly: "Weekly Stocks",
  darvas: "Darvas Box",
  day_scan: "Day Scan",
};

function formatEta(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s left`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}m ${s}s left`;
}

export default function GlobalScanProgressBar() {
  const { activeScans } = useGlobalScanMonitor();
  const [, tick] = useState(0);

  useEffect(() => {
    if (activeScans.length === 0) return;
    const id = window.setInterval(() => tick((t) => t + 1), 1000);
    return () => window.clearInterval(id);
  }, [activeScans.length]);

  const primary = activeScans[0];
  const progressPercent = useMemo(() => {
    if (!primary || primary.total <= 0) return 0;
    return Math.min(100, Math.round((primary.scanned / primary.total) * 100));
  }, [primary]);

  const etaSec = useMemo(() => {
    if (!primary || primary.scanned <= 0 || primary.total <= 0) return null;
    const elapsed = (Date.now() - primary.startedAt) / 1000;
    const rate = primary.scanned / elapsed;
    if (rate <= 0) return null;
    return (primary.total - primary.scanned) / rate;
  }, [primary]);

  if (!primary) return null;

  const label = SCAN_LABELS[primary.scanType] ?? primary.scanType;

  return (
    <div className="global-scan-bar" role="status" aria-live="polite">
      <div className="global-scan-bar-header">
        <span className="global-scan-bar-pulse">●</span>
        <strong>{label}</strong>
        <span className="global-scan-bar-count">
          {primary.scanned} / {primary.total} stocks
        </span>
        <span className="global-scan-bar-matches">{primary.matchCount} matches</span>
        {activeScans.length > 1 && (
          <span className="global-scan-bar-extra">+{activeScans.length - 1} more scan(s)</span>
        )}
      </div>
      <div className="scan-progress-bar-track global-scan-bar-track">
        <div
          className="scan-progress-bar-fill global-scan-bar-fill"
          style={{ width: `${progressPercent}%` }}
        />
      </div>
      <div className="global-scan-bar-meta">
        <span>
          {primary.currentSymbol ? `Last: ${primary.currentSymbol}` : "Scanning…"}
        </span>
        <span>
          {progressPercent}% · {etaSec != null ? formatEta(etaSec) : "calculating…"}
        </span>
      </div>
    </div>
  );
}
