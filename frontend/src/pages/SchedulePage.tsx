import { useCallback, useEffect, useState, Fragment } from "react";
import {
  fetchScanSchedules,
  fetchScanHistory,
  updateScanSchedule,
  type ScanSchedule,
  type ScanHistoryEntry,
} from "../api";
import ScheduleConfigForm from "../components/ScheduleConfigForm";
import ScanHistoryDetailPanel from "../components/ScanHistoryDetailPanel";
import { useAppSocket } from "../context/AppSocketContext";
import { useGlobalScanMonitor } from "../context/GlobalScanMonitorContext";
import ScanActivitySection from "../components/ScanActivitySection";
import { formatIST } from "../lib/formatTime";

function formatDuration(sec: number | null): string {
  if (sec == null) return "—";
  if (sec < 60) return `${Math.round(sec)}s`;
  const min = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return `${min}m ${s}s`;
}

const SCAN_TYPE_LABELS: Record<string, string> = {
  nse_stocks: "NSE Stocks",
  brst: "Year Breakout",
  multi_year: "Multi-Year Breakout",
  golden: "Golden Stocks",
  weekly: "Weekly Stocks",
  darvas: "Darvas Box",
  mean_reversion: "Mean Reversion",
  vol_squeeze: "Volatility Squeeze",
  volume_surge: "Volume Surge",
  bulk_deals: "Bulk Deals",
  sector_rotation: "Sector Rotation",
  ipo_intel: "IPO GMP & Subs Scrape",
};

export default function SchedulePage() {
  const [schedules, setSchedules] = useState<ScanSchedule[]>([]);
  const [history, setHistory] = useState<ScanHistoryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { subscribe } = useAppSocket();
  const { activeScans } = useGlobalScanMonitor();
  const [expandedHistoryId, setExpandedHistoryId] = useState<number | null>(null);

  const loadSchedules = useCallback(async () => {
    try {
      const data = await fetchScanSchedules();
      setSchedules(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load schedules");
    }
  }, []);

  const loadHistory = useCallback(async () => {
    try {
      const data = await fetchScanHistory(50);
      setHistory(data);
    } catch (err) {
      console.error("Failed to load scan history:", err);
    }
  }, []);

  useEffect(() => {
    Promise.all([loadSchedules(), loadHistory()])
      .finally(() => setLoading(false));
  }, [loadSchedules, loadHistory]);

  // Subscribe to schedule events via WebSocket
  useEffect(() => {
    const unsubStarted = subscribe("schedule:scan-started", (msg) => {
      console.log("Scheduled scan started:", msg);
      loadHistory();
    });

    const unsubComplete = subscribe("scan:complete", () => {
      loadHistory();
    });

    return () => {
      unsubStarted();
      unsubComplete();
    };
  }, [subscribe, loadHistory]);

  const handleSave = useCallback(
    async (
      scanType: string,
      config: {
        enabled: boolean;
        frequency: string;
        time_of_day: string;
        timezone: string;
      },
    ) => {
      await updateScanSchedule(scanType, config);
      await loadSchedules();
    },
    [loadSchedules],
  );

  if (loading) {
    return (
      <div className="schedule-page">
        <div className="schedule-page-header">
          <h1>Schedule Management</h1>
        </div>
        <p className="meta">Loading schedules…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="schedule-page">
        <div className="schedule-page-header">
          <h1>Schedule Management</h1>
        </div>
        <p className="error-text">{error}</p>
      </div>
    );
  }

  return (
    <div className="schedule-page">
      <div className="schedule-page-header">
        <h1>Schedule Management</h1>
        <p className="meta">
          Configure automated scan schedules and view recent activity
        </p>
      </div>

      <section className="schedule-section">
        <h2 className="schedule-section-title">Scan Schedules</h2>
        <div className="schedule-config-grid">
          {schedules.map((schedule) => (
            <ScheduleConfigForm
              key={schedule.scan_type}
              schedule={schedule}
              onSave={(config) => handleSave(schedule.scan_type, config)}
            />
          ))}
        </div>
      </section>

      {activeScans.map((scan) => {
        const pct = scan.total > 0 ? Math.round((scan.scanned / scan.total) * 100) : 0;
        return (
          <ScanActivitySection
            key={scan.scanType}
            scanning={scan.scanning}
            scanned={scan.scanned}
            total={scan.total}
            currentSymbol={scan.currentSymbol}
            progressPercent={pct}
            matchCount={scan.matchCount}
            skippedCount={scan.skippedCount}
            startedAt={scan.startedAt}
            logs={scan.logs}
            alwaysShowProgress
          />
        );
      })}

      <section className="schedule-section">
        <h2 className="schedule-section-title">Recent Scan Activity</h2>
        {history.length === 0 ? (
          <p className="meta">No scan history yet</p>
        ) : (
          <div className="schedule-history-table-wrapper">
            <table className="schedule-history-table">
              <thead>
                <tr>
                  <th>Date &amp; Time</th>
                  <th>Scan Type</th>
                  <th>Status</th>
                  <th>Duration</th>
                  <th>Matches</th>
                  <th>Scanned</th>
                  <th>Triggered By</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {history.map((entry) => (
                  <Fragment key={entry.id}>
                    <tr>
                      <td>{formatIST(entry.created_at)}</td>
                      <td>{SCAN_TYPE_LABELS[entry.scan_type] || entry.scan_type}</td>
                      <td>
                        <span
                          className={`schedule-history-status schedule-history-status-${entry.status}`}
                        >
                          {entry.status === "completed" ? "✓" : entry.status === "cancelled" ? "—" : "✗"}{" "}
                          {entry.status}
                        </span>
                      </td>
                      <td>{formatDuration(entry.duration_sec)}</td>
                      <td>{entry.matched_count ?? "—"}</td>
                      <td>{entry.total_scanned ?? "—"}</td>
                      <td>
                        <span className="schedule-history-trigger">
                          {entry.triggered_by}
                        </span>
                      </td>
                      <td>
                        <button
                          type="button"
                          className="toolbar-btn"
                          onClick={() =>
                            setExpandedHistoryId((id) => (id === entry.id ? null : entry.id))
                          }
                        >
                          {expandedHistoryId === entry.id ? "Hide" : "Log"}
                        </button>
                      </td>
                    </tr>
                    {expandedHistoryId === entry.id && (
                      <tr>
                        <td colSpan={8}>
                          <ScanHistoryDetailPanel historyId={entry.id} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
