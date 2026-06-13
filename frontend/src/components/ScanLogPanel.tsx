import { useMemo, useState } from "react";
import type { ScanLogEntry, ScanLogOutcome } from "../types/scanLog";
import { formatIST } from "../lib/formatTime";

interface ScanLogPanelProps {
  logs: ScanLogEntry[];
  title?: string;
  maxHeight?: number;
  defaultFilter?: ScanLogOutcome | "all";
  showFilters?: boolean;
}

const OUTCOME_LABELS: Record<ScanLogOutcome, string> = {
  match: "Passed",
  skip: "Skipped",
  error: "Error",
  info: "Info",
};

export default function ScanLogPanel({
  logs,
  title = "Scan log",
  maxHeight = 320,
  defaultFilter = "all",
  showFilters = true,
}: ScanLogPanelProps) {
  const [filter, setFilter] = useState<ScanLogOutcome | "all">(defaultFilter);

  const filtered = useMemo(() => {
    if (filter === "all") return logs;
    return logs.filter((l) => l.outcome === filter);
  }, [logs, filter]);

  const counts = useMemo(() => {
    const c = { match: 0, skip: 0, error: 0, info: 0 };
    for (const l of logs) {
      if (l.outcome in c) c[l.outcome as keyof typeof c] += 1;
    }
    return c;
  }, [logs]);

  return (
    <div className="scan-log-panel">
      <div className="scan-log-panel-header">
        <strong>{title}</strong>
        <span className="scan-log-panel-stats">
          {logs.length} events · {counts.match} passed · {counts.skip} skipped
          {counts.error > 0 && ` · ${counts.error} errors`}
        </span>
      </div>

      {showFilters && (
        <div className="scan-log-filters">
          {(["all", "match", "skip", "error", "info"] as const).map((f) => (
            <button
              key={f}
              type="button"
              className={`scan-log-filter-btn${filter === f ? " active" : ""}`}
              onClick={() => setFilter(f)}
            >
              {f === "all" ? "All" : OUTCOME_LABELS[f]}
              {f !== "all" && counts[f] > 0 ? ` (${counts[f]})` : ""}
            </button>
          ))}
        </div>
      )}

      <div className="scan-log-list" style={{ maxHeight }}>
        {filtered.length === 0 ? (
          <p className="meta scan-log-empty">No log entries yet. Run a scan to see per-symbol results.</p>
        ) : (
          filtered.map((entry, i) => (
            <div
              key={`${entry.ts}-${entry.symbol}-${i}`}
              className={`scan-log-row scan-log-row-${entry.outcome}`}
            >
              <span className="scan-log-time">{formatIST(entry.ts)}</span>
              <span className={`scan-log-outcome scan-log-outcome-${entry.outcome}`}>
                {OUTCOME_LABELS[entry.outcome]}
              </span>
              <span className="scan-log-symbol">{entry.symbol}</span>
              <span className="scan-log-message">{entry.message}</span>
              {entry.total > 0 && (
                <span className="scan-log-progress">
                  {entry.scanned}/{entry.total}
                </span>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
