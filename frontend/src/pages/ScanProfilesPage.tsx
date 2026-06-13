import { useCallback, useEffect, useMemo, useState, Fragment } from "react";
import {
  emailScanProfilesExport,
  exportScanProfiles,
  fetchScanHistory,
  importScanProfiles,
  runScanProfile,
  type ScanHistoryEntry,
} from "../api";
import { parseProfileBundle } from "../lib/scanConfig";
import type { ScanConfigV1, ScanProfileBundle } from "../types/scanConfig";
import { useGlobalScanMonitor } from "../context/GlobalScanMonitorContext";
import { useDayScanSync } from "../context/DayScanSyncContext";
import ScanActivitySection from "../components/ScanActivitySection";
import ScanHistoryDetailPanel from "../components/ScanHistoryDetailPanel";
import { formatIST } from "../lib/formatTime";

const SCAN_LABELS: Record<string, string> = {
  brst: "Year Breakout",
  multi_year: "Multi-Year Breakout",
  darvas: "Darvas Box",
  golden: "Golden Stocks",
  weekly: "Weekly Stocks",
};

interface ScannerMeta {
  scanType: string;
  label: string;
  icon: string;
  route: string;
}

const SCANNERS: ScannerMeta[] = [
  { scanType: "golden", label: "Golden Stocks", icon: "✨", route: "/golden-stocks" },
  { scanType: "weekly", label: "Weekly Stocks", icon: "📆", route: "/weekly-stocks" },
  { scanType: "brst", label: "Year Breakout", icon: "📈", route: "/brst" },
  { scanType: "multi_year", label: "Multi-Year Breakout", icon: "📊", route: "/multi-year-breakout" },
  { scanType: "darvas", label: "Darvas Box", icon: "📦", route: "/darvas-box" },
];

function formatDuration(sec: number | null): string {
  if (sec == null) return "—";
  if (sec < 60) return `${Math.round(sec)}s`;
  const min = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return `${min}m ${s}s`;
}

function minimalConfig(scanType: string): ScanConfigV1 {
  return {
    version: 1,
    scan_type: scanType,
    core_criteria: [],
    scan_params: {},
    display_filters: {},
    universe: {},
  };
}

export default function ScanProfilesPage() {
  const [bundle, setBundle] = useState<ScanProfileBundle | null>(null);
  const [savedProfiles, setSavedProfiles] = useState<Record<string, ScanConfigV1>>({});
  const [history, setHistory] = useState<ScanHistoryEntry[]>([]);
  const [expandedHistoryId, setExpandedHistoryId] = useState<number | null>(null);
  const [importErrors, setImportErrors] = useState<string[]>([]);
  const [status, setStatus] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const { activeScans, getScan } = useGlobalScanMonitor();
  const daySync = useDayScanSync();

  const loadSavedProfiles = useCallback(async () => {
    try {
      const data = await exportScanProfiles();
      const map: Record<string, ScanConfigV1> = {};
      for (const p of data.profiles) map[p.scan_type] = p;
      setSavedProfiles(map);
    } catch (err) {
      console.error("Failed to load saved scan profiles:", err);
    }
  }, []);

  const loadHistory = useCallback(async () => {
    try {
      const data = await fetchScanHistory(30);
      setHistory(data);
    } catch (err) {
      console.error("Failed to load scan history:", err);
    }
  }, []);

  useEffect(() => {
    void loadHistory();
    void loadSavedProfiles();
  }, [loadHistory, loadSavedProfiles]);

  useEffect(() => {
    if (activeScans.length === 0) {
      void loadHistory();
      void loadSavedProfiles();
    }
  }, [activeScans.length, loadHistory, loadSavedProfiles]);

  const handleRunScanner = useCallback(
    async (scanType: string) => {
      setStatus(null);
      const profile = savedProfiles[scanType] ?? minimalConfig(scanType);
      try {
        const res = await runScanProfile(profile);
        setStatus(
          res.started
            ? `Started ${SCAN_LABELS[scanType] ?? scanType} scan — watch progress above.`
            : `Could not start ${SCAN_LABELS[scanType] ?? scanType} (may already be running).`,
        );
      } catch (err) {
        setStatus(err instanceof Error ? err.message : "Run failed");
      }
    },
    [savedProfiles],
  );

  const lastNseSync = useMemo(() => daySync.lastSyncAt, [daySync.lastSyncAt]);

  const handleExport = async () => {
    setLoading(true);
    setStatus(null);
    try {
      const data = await exportScanProfiles();
      setBundle(data);
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `scan-profiles-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
      setStatus(`Exported ${data.profiles.length} profile(s).`);
    } catch (err) {
      setStatus(err instanceof Error ? err.message : "Export failed");
    } finally {
      setLoading(false);
    }
  };

  const handleImportFile = useCallback(async (file: File) => {
    setLoading(true);
    setStatus(null);
    setImportErrors([]);
    try {
      const text = await file.text();
      const { bundle: parsed, errors } = parseProfileBundle(text);
      if (!parsed || errors.length) {
        setImportErrors(errors.length ? errors : ["Invalid bundle"]);
        return;
      }
      const validated = await importScanProfiles(parsed);
      if (!validated.valid) {
        setImportErrors(validated.errors);
        return;
      }
      setBundle(parsed);
      setStatus(`Imported ${validated.profile_count} profile(s). Ready to run.`);
    } catch (err) {
      setStatus(err instanceof Error ? err.message : "Import failed");
    } finally {
      setLoading(false);
    }
  }, []);

  const handleRunProfile = async (profile: ScanConfigV1) => {
    setStatus(null);
    try {
      const res = await runScanProfile(profile);
      setStatus(
        res.started
          ? `Started ${SCAN_LABELS[profile.scan_type] ?? profile.scan_type} scan — watch progress below.`
          : `Could not start ${profile.scan_type} scan (may already be running).`,
      );
    } catch (err) {
      setStatus(err instanceof Error ? err.message : "Run failed");
    }
  };

  const handleRunAll = async () => {
    if (!bundle?.profiles.length) return;
    for (const p of bundle.profiles) {
      await handleRunProfile(p);
    }
  };

  const handleEmailExport = async () => {
    setLoading(true);
    try {
      const res = await emailScanProfilesExport();
      setStatus(res.sent ? `Emailed ${res.profiles} profile(s).` : "Email failed — check RESEND_API_KEY");
    } catch (err) {
      setStatus(err instanceof Error ? err.message : "Email failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page-container scan-profiles-page">
      <div className="page-header">
        <div>
          <h1>Scan Profiles</h1>
          <p className="page-subtitle">
            Trigger any scanner with one click. Parameters are read-only here — change them inside
            the respective screener (they are saved to the database). Live progress shows above.
          </p>
        </div>
      </div>

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
            logTitle={`${SCAN_LABELS[scan.scanType] ?? scan.scanType} — live log`}
          />
        );
      })}

      {status && <p className="status">{status}</p>}
      {importErrors.length > 0 && (
        <div className="status error">
          {importErrors.map((e) => (
            <div key={e}>{e}</div>
          ))}
        </div>
      )}

      <div className="scan-trigger-grid">
        {SCANNERS.map((sc) => {
          const live = getScan(sc.scanType);
          const profile = savedProfiles[sc.scanType];
          const params = profile?.scan_params ?? {};
          const paramKeys = Object.keys(params);
          return (
            <div
              key={sc.scanType}
              className={`scan-trigger-card${live.scanning ? " running" : ""}`}
            >
              <div className="scan-trigger-head">
                <span className="scan-trigger-icon" aria-hidden="true">
                  {sc.icon}
                </span>
                <div>
                  <div className="scan-trigger-title">{sc.label}</div>
                  <div className="scan-trigger-sub">Edit parameters in screener</div>
                </div>
              </div>

              <div className="scan-trigger-meta">
                <div className="scan-trigger-meta-row">
                  <span>Last scanned</span>
                  <strong>
                    {profile?.last_scanned_at
                      ? formatIST(profile.last_scanned_at)
                      : "Never"}
                  </strong>
                </div>
                <div className="scan-trigger-meta-row">
                  <span>Matches</span>
                  <strong>{profile?.match_count ?? "—"}</strong>
                </div>
              </div>

              {paramKeys.length > 0 ? (
                <div className="scan-trigger-params">
                  {paramKeys.map((k) => (
                    <span key={k} className="scan-trigger-param-chip">
                      {k}: {String((params as Record<string, unknown>)[k])}
                    </span>
                  ))}
                </div>
              ) : (
                <div className="scan-trigger-params-empty">Default parameters</div>
              )}

              <button
                type="button"
                className="toolbar-btn btn-primary scan-trigger-run"
                onClick={() => void handleRunScanner(sc.scanType)}
                disabled={live.scanning}
              >
                {live.scanning ? `Running ${live.scanned}/${live.total}…` : "▶ Run scan"}
              </button>
            </div>
          );
        })}

        <div className={`scan-trigger-card${daySync.syncing ? " running" : ""}`}>
          <div className="scan-trigger-head">
            <span className="scan-trigger-icon" aria-hidden="true">
              🗃️
            </span>
            <div>
              <div className="scan-trigger-title">NSE Data Sync</div>
              <div className="scan-trigger-sub">Daily prices &amp; fundamentals</div>
            </div>
          </div>

          <div className="scan-trigger-meta">
            <div className="scan-trigger-meta-row">
              <span>Last synced</span>
              <strong>{lastNseSync ? formatIST(lastNseSync) : "Never"}</strong>
            </div>
            <div className="scan-trigger-meta-row">
              <span>Status</span>
              <strong>
                {daySync.syncing
                  ? "Syncing…"
                  : daySync.needsSync
                    ? "Update available"
                    : "Up to date"}
              </strong>
            </div>
          </div>
          <div className="scan-trigger-params-empty">Full NSE universe</div>

          <button
            type="button"
            className="toolbar-btn btn-primary scan-trigger-run"
            onClick={() => daySync.startSync(true)}
            disabled={daySync.syncing}
          >
            {daySync.syncing
              ? `Syncing ${daySync.job?.processed ?? 0}/${daySync.job?.total ?? 0}…`
              : "↻ Sync now"}
          </button>
        </div>
      </div>

      <details className="scan-advanced">
        <summary>Advanced: import / export / email profiles</summary>
        <div className="scan-advanced-body">
          <div className="scan-profiles-actions">
            <button
              type="button"
              className="toolbar-btn btn-primary"
              onClick={() => void handleExport()}
              disabled={loading}
            >
              Export saved profiles
            </button>
            <label className="toolbar-btn">
              Import JSON
              <input
                type="file"
                accept="application/json,.json"
                hidden
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) void handleImportFile(f);
                  e.target.value = "";
                }}
              />
            </label>
            <button
              type="button"
              className="toolbar-btn"
              onClick={() => void handleEmailExport()}
              disabled={loading}
            >
              Email profiles JSON
            </button>
            {bundle && bundle.profiles.length > 1 && (
              <button type="button" className="toolbar-btn" onClick={() => void handleRunAll()}>
                Run all imported
              </button>
            )}
          </div>

          {bundle && bundle.profiles.length > 0 && (
            <div className="scan-profiles-list">
              <h3>Imported profiles ({bundle.profiles.length})</h3>
              {bundle.profiles.map((p, i) => {
                const live = getScan(p.scan_type);
                return (
                  <div key={`${p.scan_type}-${i}`} className="scan-profile-card">
                    <div className="scan-profile-card-header">
                      <strong>{SCAN_LABELS[p.scan_type] ?? p.name ?? p.scan_type}</strong>
                      {p.last_scanned_at && (
                        <span className="scan-profile-meta">
                          Last scan: {new Date(p.last_scanned_at).toLocaleString()}
                        </span>
                      )}
                    </div>
                    {p.scan_params && Object.keys(p.scan_params).length > 0 && (
                      <div className="scan-profile-params">
                        {Object.entries(p.scan_params).map(([k, v]) => (
                          <span key={k} className="active-filter-tag">
                            {k}: {String(v)}
                          </span>
                        ))}
                      </div>
                    )}
                    <div className="scan-profile-actions">
                      <button
                        type="button"
                        className="toolbar-btn btn-primary"
                        onClick={() => void handleRunProfile(p)}
                        disabled={live.scanning}
                      >
                        {live.scanning ? "Scan running…" : "Run this scan"}
                      </button>
                    </div>
                    <details className="scan-profile-json">
                      <summary>View JSON</summary>
                      <pre>{JSON.stringify(p, null, 2)}</pre>
                    </details>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </details>

      <section className="scan-profiles-history">
        <h3>Recent scan runs</h3>
        {history.length === 0 ? (
          <p className="meta">No scan history yet. Run a scanner to see detailed logs here.</p>
        ) : (
          <div className="schedule-history-table-wrapper">
            <table className="schedule-history-table">
              <thead>
                <tr>
                  <th>Date &amp; Time</th>
                  <th>Scanner</th>
                  <th>Status</th>
                  <th>Progress</th>
                  <th>Passed</th>
                  <th>Skipped</th>
                  <th>Duration</th>
                  <th>Source</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {history.map((entry) => (
                  <Fragment key={entry.id}>
                    <tr>
                      <td>{formatIST(entry.created_at)}</td>
                      <td>{SCAN_LABELS[entry.scan_type] ?? entry.scan_type}</td>
                      <td>
                        <span
                          className={`schedule-history-status schedule-history-status-${entry.status}`}
                        >
                          {entry.status}
                        </span>
                      </td>
                      <td>
                        {entry.total_scanned != null ? `${entry.total_scanned} symbols` : "—"}
                      </td>
                      <td>{entry.matched_count ?? "—"}</td>
                      <td>{entry.skipped_count ?? "—"}</td>
                      <td>{formatDuration(entry.duration_sec)}</td>
                      <td>{entry.triggered_by}</td>
                      <td>
                        <button
                          type="button"
                          className="toolbar-btn"
                          onClick={() =>
                            setExpandedHistoryId((id) => (id === entry.id ? null : entry.id))
                          }
                        >
                          {expandedHistoryId === entry.id ? "Hide log" : "View log"}
                        </button>
                      </td>
                    </tr>
                    {expandedHistoryId === entry.id && (
                      <tr>
                        <td colSpan={9}>
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
