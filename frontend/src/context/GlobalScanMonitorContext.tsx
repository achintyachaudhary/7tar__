import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useAppSocket } from "./AppSocketContext";
import type { ActiveScanState, ScanLogEntry } from "../types/scanLog";

const SCAN_TYPES = [
  "brst",
  "multi_year",
  "golden",
  "weekly",
  "darvas",
  "mean_reversion",
  "vol_squeeze",
  "volume_surge",
  "day_scan",
] as const;

function emptyState(scanType: string): ActiveScanState {
  return {
    scanType,
    scanning: false,
    scanned: 0,
    total: 0,
    currentSymbol: "",
    matchCount: 0,
    skippedCount: 0,
    logs: [],
    startedAt: 0,
    historyId: null,
  };
}

function parseLog(msg: Record<string, unknown>): ScanLogEntry | null {
  if (!msg.ts || !msg.symbol) return null;
  return {
    ts: String(msg.ts),
    symbol: String(msg.symbol),
    outcome: (msg.outcome as ScanLogEntry["outcome"]) ?? "info",
    message: String(msg.message ?? ""),
    scanned: Number(msg.scanned ?? 0),
    total: Number(msg.total ?? 0),
    match_count: Number(msg.match_count ?? 0),
  };
}

interface GlobalScanMonitorContextValue {
  scans: Record<string, ActiveScanState>;
  activeScans: ActiveScanState[];
  getScan: (scanType: string) => ActiveScanState;
}

const GlobalScanMonitorContext = createContext<GlobalScanMonitorContextValue | null>(null);

export function GlobalScanMonitorProvider({ children }: { children: ReactNode }) {
  const { subscribe, sendMessage, connected } = useAppSocket();
  const [scans, setScans] = useState<Record<string, ActiveScanState>>({});

  const updateScan = useCallback((scanType: string, patch: Partial<ActiveScanState>) => {
    setScans((prev) => ({
      ...prev,
      [scanType]: { ...(prev[scanType] ?? emptyState(scanType)), ...patch, scanType },
    }));
  }, []);

  const appendLog = useCallback((scanType: string, entry: ScanLogEntry) => {
    setScans((prev) => {
      const cur = prev[scanType] ?? emptyState(scanType);
      const last = cur.logs[cur.logs.length - 1];
      if (
        last
        && last.symbol === entry.symbol
        && last.outcome === entry.outcome
        && last.message === entry.message
        && last.scanned === entry.scanned
      ) {
        return prev;
      }
      const logs = [...cur.logs, entry].slice(-2000);
      return {
        ...prev,
        [scanType]: {
          ...cur,
          logs,
          scanned: entry.scanned || cur.scanned,
          total: entry.total || cur.total,
          matchCount: entry.match_count ?? cur.matchCount,
        },
      };
    });
  }, []);

  useEffect(() => {
    if (!connected) return;
    sendMessage("scan:status", {});
    SCAN_TYPES.forEach((st) => sendMessage("scan:status", { scan_type: st }));
  }, [connected, sendMessage]);

  useEffect(() => {
    const unsubs: (() => void)[] = [];

    unsubs.push(
      subscribe("scan:init", (msg) => {
        const scanType = String(msg.scan_type ?? "");
        if (!scanType) return;
        updateScan(scanType, {
          scanning: true,
          scanned: 0,
          total: Number(msg.total ?? 0),
          currentSymbol: "",
          matchCount: 0,
          skippedCount: 0,
          logs: [],
          startedAt: Date.now(),
          historyId: null,
        });
      }),
    );

    unsubs.push(
      subscribe("scan:progress", (msg) => {
        const scanType = String(msg.scan_type ?? "");
        if (!scanType) return;
        updateScan(scanType, {
          scanning: true,
          scanned: Number(msg.scanned ?? 0),
          total: Number(msg.total ?? 0),
          currentSymbol: String(msg.symbol ?? ""),
          matchCount: Number(msg.match_count ?? 0),
          skippedCount: Number(msg.skipped_count ?? 0),
        });
      }),
    );

    unsubs.push(
      subscribe("scan:log", (msg) => {
        const scanType = String(msg.scan_type ?? "");
        const entry = parseLog(msg);
        if (!scanType || !entry) return;
        appendLog(scanType, entry);
      }),
    );

    unsubs.push(
      subscribe("scan:running", (msg) => {
        const scanType = String(msg.scan_type ?? "");
        if (!scanType || msg.running !== true) return;
        const logs = Array.isArray(msg.logs) ? (msg.logs as ScanLogEntry[]) : [];
        updateScan(scanType, {
          scanning: true,
          scanned: Number(msg.scanned ?? 0),
          total: Number(msg.total ?? 0),
          currentSymbol: String(msg.symbol ?? ""),
          matchCount: Number(msg.match_count ?? 0),
          startedAt: Date.now(),
          ...(logs.length ? { logs } : {}),
        });
      }),
    );

    unsubs.push(
      subscribe("scan:complete", (msg) => {
        const scanType = String(msg.scan_type ?? "");
        if (!scanType) return;
        updateScan(scanType, {
          scanning: false,
          scanned: Number(msg.scanned ?? 0),
          total: Number(msg.total ?? 0),
          matchCount: Number(msg.count ?? 0),
          historyId: msg.history_id != null ? Number(msg.history_id) : null,
        });
      }),
    );

    const handleStop = (msg: Record<string, unknown>) => {
      const scanType = String(msg.scan_type ?? "");
      if (!scanType) return;
      updateScan(scanType, { scanning: false });
    };

    unsubs.push(subscribe("scan:cancelled", handleStop));
    unsubs.push(subscribe("scan:error", handleStop));

    return () => unsubs.forEach((u) => u());
  }, [subscribe, updateScan, appendLog]);

  const activeScans = useMemo(
    () => Object.values(scans).filter((s) => s.scanning),
    [scans],
  );

  const getScan = useCallback(
    (scanType: string) => scans[scanType] ?? emptyState(scanType),
    [scans],
  );

  const value = useMemo(
    () => ({ scans, activeScans, getScan }),
    [scans, activeScans, getScan],
  );

  return (
    <GlobalScanMonitorContext.Provider value={value}>
      {children}
    </GlobalScanMonitorContext.Provider>
  );
}

export function useGlobalScanMonitor() {
  const ctx = useContext(GlobalScanMonitorContext);
  if (!ctx) {
    throw new Error("useGlobalScanMonitor must be used within GlobalScanMonitorProvider");
  }
  return ctx;
}
