import { useEffect, useState } from "react";
import { fetchScanHistoryDetail } from "../api";
import type { ScanHistoryDetail } from "../api";
import ScanLogPanel from "./ScanLogPanel";
import type { ScanLogEntry } from "../types/scanLog";
import { formatIST } from "../lib/formatTime";

interface ScanHistoryDetailPanelProps {
  historyId: number;
}

function buildLogsFromDetails(details: ScanHistoryDetail["details"]): ScanLogEntry[] {
  if (!details) return [];
  if (details.log_tail?.length) {
    return details.log_tail as ScanLogEntry[];
  }
  const logs: ScanLogEntry[] = [];
  const total = details.total ?? 0;
  let i = 0;
  for (const sym of details.matched_symbols ?? []) {
    i += 1;
    logs.push({
      ts: "",
      symbol: sym,
      outcome: "match",
      message: "matched",
      scanned: i,
      total,
      match_count: i,
    });
  }
  for (const sym of details.skipped_symbols ?? []) {
    i += 1;
    logs.push({
      ts: "",
      symbol: sym,
      outcome: "skip",
      message: "no match",
      scanned: i,
      total,
      match_count: details.matched_count ?? 0,
    });
  }
  for (const err of details.errors ?? []) {
    logs.push({
      ts: "",
      symbol: err.symbol,
      outcome: "error",
      message: err.error,
      scanned: 0,
      total,
      match_count: details.matched_count ?? 0,
    });
  }
  return logs;
}

export default function ScanHistoryDetailPanel({ historyId }: ScanHistoryDetailPanelProps) {
  const [entry, setEntry] = useState<ScanHistoryDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetchScanHistoryDetail(historyId)
      .then(setEntry)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load details"))
      .finally(() => setLoading(false));
  }, [historyId]);

  if (loading) return <p className="meta">Loading scan details…</p>;
  if (error) return <p className="error-text">{error}</p>;
  if (!entry) return null;

  const details = entry.details;
  const logs = buildLogsFromDetails(details);

  return (
    <div className="scan-history-detail">
      <div className="scan-history-detail-summary">
        <span>Scanned {entry.total_scanned ?? details?.scanned ?? "—"} symbols</span>
        <span>{entry.matched_count ?? 0} passed</span>
        <span>{details?.skipped_count ?? 0} skipped</span>
        {(details?.error_count ?? 0) > 0 && <span>{details?.error_count} errors</span>}
        {entry.duration_sec != null && <span>{Math.round(entry.duration_sec)}s duration</span>}
        {entry.error_message && (
          <span className="error-text">{entry.error_message}</span>
        )}
      </div>

      {details?.matched_symbols && details.matched_symbols.length > 0 && (
        <div className="scan-history-matched">
          <strong>Passed ({details.matched_symbols.length}):</strong>{" "}
          {details.matched_symbols.join(", ")}
        </div>
      )}

      {details?.scan_config && (
        <details className="scan-profile-json">
          <summary>Scan parameters used</summary>
          <pre>{JSON.stringify(details.scan_config, null, 2)}</pre>
        </details>
      )}

      {logs.length > 0 ? (
        <ScanLogPanel
          logs={logs}
          title={`Run log · ${formatIST(entry.created_at)}`}
          maxHeight={400}
        />
      ) : (
        <p className="meta">No per-symbol log stored for this run.</p>
      )}
    </div>
  );
}
