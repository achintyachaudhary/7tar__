import { useCallback, useEffect, useRef, useState } from "react";
import { useAppSocket } from "../context/AppSocketContext";
import { getCachedScanResults, cacheScanResults } from "../lib/dbFirstStorage";
import type { ScanConfigV1 } from "../types/scanConfig";

export interface ScanChannelState<T = Record<string, unknown>> {
  scanning: boolean;
  scanned: number;
  total: number;
  currentSymbol: string;
  matches: T[];
  error: string | null;
  lastScannedAt: Date | null;
  lastScanFilters: Record<string, unknown> | null;
  lastScanConfig: ScanConfigV1 | null;
  loadedFromDb: boolean;
  startScan: (filters?: Record<string, unknown>) => void;
  cancelScan: () => void;
}

interface UseScanChannelOptions<T> {
  fetchCached?: () => Promise<{
    matches: T[] | unknown[];
    scanned: number;
    total: number;
    last_scanned_at: string | null;
    filter?: Record<string, unknown>;
  }>;
}

interface LiveScanStatus<T> {
  running?: boolean;
  scanned?: number;
  total?: number;
  symbol?: string;
  matches?: T[];
}

function parseLiveStatus<T>(msg: Record<string, unknown>): LiveScanStatus<T> | null {
  if (msg.running !== true) return null;
  return {
    running: true,
    scanned: Number(msg.scanned ?? 0),
    total: Number(msg.total ?? 0),
    symbol: String(msg.symbol ?? ""),
    matches: Array.isArray(msg.matches) ? (msg.matches as T[]) : undefined,
  };
}

function isAlreadyRunningMessage(message: string): boolean {
  return message.toLowerCase().includes("already running");
}

export function useScanChannel<T = Record<string, unknown>>(
  scanType: string,
  options: UseScanChannelOptions<T> = {},
): ScanChannelState<T> {
  const { sendMessage, subscribe, connected } = useAppSocket();
  const [scanning, setScanning] = useState(false);
  const [scanned, setScanned] = useState(0);
  const [total, setTotal] = useState(0);
  const [currentSymbol, setCurrentSymbol] = useState("");
  const [matches, setMatches] = useState<T[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [lastScannedAt, setLastScannedAt] = useState<Date | null>(null);
  const [lastScanFilters, setLastScanFilters] = useState<Record<string, unknown> | null>(null);
  const [lastScanConfig, setLastScanConfig] = useState<ScanConfigV1 | null>(null);
  const [loadedFromDb, setLoadedFromDb] = useState(false);
  const isMounted = useRef(true);

  const applyLiveStatus = useCallback((status: LiveScanStatus<T>) => {
    setScanning(true);
    setError(null);
    setScanned(status.scanned ?? 0);
    setTotal(status.total ?? 0);
    setCurrentSymbol(status.symbol ?? "");
    if (status.matches) {
      setMatches(status.matches);
    }
  }, []);

  const applyCachedPayload = useCallback((data: {
    matches: T[] | unknown[];
    scanned: number;
    total: number;
    last_scanned_at: string | null;
    filter?: Record<string, unknown>;
  }) => {
    if (!data.last_scanned_at) return;
    setMatches(data.matches as T[]);
    setScanned(data.scanned);
    setTotal(data.total);
    setLastScannedAt(new Date(data.last_scanned_at));
    const filt = data.filter ?? {};
    const cfg = filt.scan_config;
    if (cfg && typeof cfg === "object") {
      setLastScanConfig(cfg as ScanConfigV1);
      const df = (cfg as ScanConfigV1).display_filters;
      if (df && typeof df === "object") {
        setLastScanFilters(df as Record<string, unknown>);
      }
    } else {
      const uiFilters = filt.ui_filters;
      if (uiFilters && typeof uiFilters === "object") {
        setLastScanFilters(uiFilters as Record<string, unknown>);
      }
    }
  }, []);

  const requestLiveStatus = useCallback(() => {
    sendMessage("scan:status", { scan_type: scanType });
  }, [sendMessage, scanType]);

  const fetchLiveStatus = useCallback(async () => {
    try {
      const res = await fetch(`/api/scans/status?scan_type=${encodeURIComponent(scanType)}`);
      if (!res.ok) return;
      const data = (await res.json()) as Record<string, unknown>;
      if (!isMounted.current) return;
      const live = parseLiveStatus<T>(data);
      if (live) applyLiveStatus(live);
    } catch {
      // non-fatal
    }
  }, [scanType, applyLiveStatus]);

  const attachToRunningScan = useCallback(() => {
    setError(null);
    requestLiveStatus();
    void fetchLiveStatus();
  }, [requestLiveStatus, fetchLiveStatus]);

  // Load cached results: localStorage first (instant), then DB
  useEffect(() => {
    isMounted.current = true;

    const cached = getCachedScanResults(scanType);
    if (cached && cached.last_scanned_at) {
      applyCachedPayload(cached as {
        matches: T[];
        scanned: number;
        total: number;
        last_scanned_at: string;
        filter?: Record<string, unknown>;
      });
    }

    if (options.fetchCached) {
      options.fetchCached()
        .then((data) => {
          if (!isMounted.current) return;
          if (data.last_scanned_at) {
            applyCachedPayload(data);
            cacheScanResults(scanType, data);
          }
        })
        .catch((err) => {
          console.error(`Failed to load ${scanType} scan results from DB:`, err);
        })
        .finally(() => {
          if (isMounted.current) setLoadedFromDb(true);
        });
    } else {
      setLoadedFromDb(true);
    }

    void fetchLiveStatus();

    return () => {
      isMounted.current = false;
    };
  }, [scanType, applyCachedPayload, options.fetchCached, fetchLiveStatus]);

  // Re-sync when WebSocket reconnects
  useEffect(() => {
    if (!connected) return;
    requestLiveStatus();
    void fetchLiveStatus();
  }, [connected, requestLiveStatus, fetchLiveStatus]);

  // Subscribe to WS channels
  useEffect(() => {
    const unsubs: (() => void)[] = [];

    unsubs.push(
      subscribe("scan:status", (msg) => {
        if (msg.scan_type !== scanType) return;
        const status = msg.status as Record<string, unknown> | undefined;
        if (!status) return;
        const live = parseLiveStatus<T>(status);
        if (live) {
          applyLiveStatus(live);
        } else if (status.running === false) {
          setScanning(false);
        }
      }),
    );

    unsubs.push(
      subscribe("scan:running", (msg) => {
        if (msg.scan_type !== scanType) return;
        const live = parseLiveStatus<T>(msg);
        if (live) applyLiveStatus(live);
      }),
    );

    unsubs.push(
      subscribe("scan:init", (msg) => {
        if (msg.scan_type !== scanType) return;
        setScanning(true);
        setError(null);
        setScanned(0);
        setTotal(msg.total as number);
        setCurrentSymbol("");
        setMatches([]);
      }),
    );

    unsubs.push(
      subscribe("scan:progress", (msg) => {
        if (msg.scan_type !== scanType) return;
        setScanning(true);
        setError(null);
        setScanned(msg.scanned as number);
        if (msg.total) setTotal(msg.total as number);
        setCurrentSymbol(msg.symbol as string);
      }),
    );

    unsubs.push(
      subscribe("scan:match", (msg) => {
        if (msg.scan_type !== scanType) return;
        setScanning(true);
        setError(null);
        setMatches((prev) => [...prev, msg.data as T]);
      }),
    );

    unsubs.push(
      subscribe("scan:complete", (msg) => {
        if (msg.scan_type !== scanType) return;
        setScanning(false);
        setLastScannedAt(new Date());

        if (options.fetchCached) {
          options.fetchCached()
            .then((data) => {
              if (!isMounted.current) return;
              if (data.last_scanned_at) {
                applyCachedPayload(data);
                cacheScanResults(scanType, data);
              }
            })
            .catch((err) => {
              console.error(`Failed to cache ${scanType} scan results:`, err);
            });
        }
      }),
    );

    unsubs.push(
      subscribe("scan:error", (msg) => {
        if (msg.scan_type !== scanType) return;
        const message = String(msg.message ?? "");
        if (isAlreadyRunningMessage(message)) {
          attachToRunningScan();
          return;
        }
        setError(message);
        setScanning(false);
      }),
    );

    unsubs.push(
      subscribe("scan:cancelled", (msg) => {
        if (msg.scan_type !== scanType) return;
        setScanning(false);
      }),
    );

    return () => unsubs.forEach((u) => u());
  }, [
    subscribe,
    scanType,
    applyCachedPayload,
    applyLiveStatus,
    attachToRunningScan,
    options.fetchCached,
  ]);

  const startScan = useCallback(
    (filters: Record<string, unknown> = {}) => {
      setScanning(true);
      setError(null);
      sendMessage("scan:start", { scan_type: scanType, filters });
      requestLiveStatus();
      window.setTimeout(() => {
        void fetchLiveStatus();
      }, 400);
    },
    [sendMessage, scanType, requestLiveStatus, fetchLiveStatus],
  );

  const cancelScan = useCallback(() => {
    sendMessage("scan:cancel", { scan_type: scanType });
    setScanning(false);
  }, [sendMessage, scanType]);

  return {
    scanning,
    scanned,
    total,
    currentSymbol,
    matches,
    error,
    lastScannedAt,
    lastScanFilters,
    lastScanConfig,
    loadedFromDb,
    startScan,
    cancelScan,
  };
}
