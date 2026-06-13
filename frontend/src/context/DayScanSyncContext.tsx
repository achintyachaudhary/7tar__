import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { fetchDayScanSyncStatus } from "../api";
import type { DayScanStatus, DayScanSyncStatus } from "../types/dayScan";
import { useAppSocket } from "./AppSocketContext";

interface DayScanSyncState {
  syncThroughDate: string | null;
  expectedThroughDate: string | null;
  lastSyncAt: string | null;
  needsSync: boolean;
  syncing: boolean;
  job: DayScanStatus | null;
  error: string | null;
  refreshCounter: number;
}

interface DayScanSyncContextValue extends DayScanSyncState {
  startSync: (force?: boolean) => void;
  refreshSyncStatus: () => Promise<void>;
}

const DayScanSyncContext = createContext<DayScanSyncContextValue | null>(null);

const DAY_SCAN_TYPE = "day_scan";

function applySyncStatus(
  sync: DayScanSyncStatus,
  setters: {
    setSyncThroughDate: (v: string | null) => void;
    setExpectedThroughDate: (v: string | null) => void;
    setLastSyncAt: (v: string | null) => void;
    setNeedsSync: (v: boolean) => void;
    setSyncing: (v: boolean) => void;
  },
) {
  setters.setSyncThroughDate(sync.sync_through_date);
  setters.setExpectedThroughDate(sync.expected_through_date);
  setters.setLastSyncAt(sync.last_sync_at);
  setters.setNeedsSync(sync.needs_sync);
  setters.setSyncing(sync.running);
}

export function DayScanSyncProvider({ children }: { children: ReactNode }) {
  const [syncThroughDate, setSyncThroughDate] = useState<string | null>(null);
  const [expectedThroughDate, setExpectedThroughDate] = useState<string | null>(null);
  const [lastSyncAt, setLastSyncAt] = useState<string | null>(null);
  const [needsSync, setNeedsSync] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [job, setJob] = useState<DayScanStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshCounter, setRefreshCounter] = useState(0);

  const { sendMessage, subscribe } = useAppSocket();
  const autoStartedRef = useRef(false);

  const setters = useMemo(
    () => ({
      setSyncThroughDate,
      setExpectedThroughDate,
      setLastSyncAt,
      setNeedsSync,
      setSyncing,
    }),
    [],
  );

  const refreshSyncStatus = useCallback(async () => {
    const sync = await fetchDayScanSyncStatus();
    applySyncStatus(sync, setters);
    return;
  }, [setters]);

  const startSync = useCallback(
    (force = false) => {
      setError(null);
      setSyncing(true);
      sendMessage("scan:start", {
        scan_type: DAY_SCAN_TYPE,
        filters: { force },
      });
    },
    [sendMessage],
  );

  // Initial sync check — load status on mount
  useEffect(() => {
    fetchDayScanSyncStatus()
      .then((sync) => {
        applySyncStatus(sync, setters);
        if (sync.needs_sync && !autoStartedRef.current) {
          autoStartedRef.current = true;
          startSync(false);
        }
      })
      .catch((err) => {
        console.error("Failed to load day scan sync status:", err);
      });
  }, [setters, startSync]);

  // Subscribe to scan progress events via unified WebSocket
  useEffect(() => {
    const unsubProgress = subscribe("scan:progress", (msg) => {
      if (msg.scan_type !== DAY_SCAN_TYPE) return;
      
      setJob({
        running: true,
        total: (msg.total as number) || 0,
        processed: (msg.scanned as number) || 0,
        fetched: 0,
        skipped: 0,
        failed: 0,
        current_symbol: (msg.symbol as string) || "",
        started_at: null,
        completed_at: null,
        error: null,
      });
      setSyncing(true);
    });

    const unsubComplete = subscribe("scan:complete", (msg) => {
      if (msg.scan_type !== DAY_SCAN_TYPE) return;
      
      setSyncing(false);
      setRefreshCounter((c) => c + 1);
      
      // Refresh sync status after completion
      refreshSyncStatus();
    });

    const unsubRunning = subscribe("scan:running", (msg) => {
      if (msg.scan_type !== DAY_SCAN_TYPE) return;
      if (msg.running !== true) return;

      setError(null);
      setSyncing(true);
      setJob({
        running: true,
        total: (msg.total as number) || 0,
        processed: (msg.scanned as number) || 0,
        fetched: 0,
        skipped: 0,
        failed: 0,
        current_symbol: (msg.symbol as string) || "",
        started_at: null,
        completed_at: null,
        error: null,
      });
    });

    const unsubError = subscribe("scan:error", (msg) => {
      if (msg.scan_type !== DAY_SCAN_TYPE) return;

      const message = String(msg.message ?? "");
      if (message.toLowerCase().includes("already running")) {
        setError(null);
        sendMessage("scan:status", { scan_type: DAY_SCAN_TYPE });
        return;
      }

      setError(message || "Sync failed");
      setSyncing(false);
    });

    return () => {
      unsubProgress();
      unsubComplete();
      unsubRunning();
      unsubError();
    };
  }, [subscribe, refreshSyncStatus, sendMessage]);

  const value = useMemo<DayScanSyncContextValue>(
    () => ({
      syncThroughDate,
      expectedThroughDate,
      lastSyncAt,
      needsSync,
      syncing,
      job,
      error,
      refreshCounter,
      startSync,
      refreshSyncStatus,
    }),
    [
      syncThroughDate,
      expectedThroughDate,
      lastSyncAt,
      needsSync,
      syncing,
      job,
      error,
      refreshCounter,
      startSync,
      refreshSyncStatus,
    ],
  );

  return <DayScanSyncContext.Provider value={value}>{children}</DayScanSyncContext.Provider>;
}

export function useDayScanSync(): DayScanSyncContextValue {
  const ctx = useContext(DayScanSyncContext);
  if (!ctx) {
    throw new Error("useDayScanSync must be used within DayScanSyncProvider");
  }
  return ctx;
}
