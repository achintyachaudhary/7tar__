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
import { fetchMultiYearScanResults } from "../api";
import type { MultiYearMatch } from "../types/multiYear";

interface MultiYearScanState {
  scanning: boolean;
  scanned: number;
  total: number;
  currentSymbol: string;
  matches: MultiYearMatch[];
  error: string | null;
  lastScannedAt: Date | null;
  loadedFromDb: boolean;
}

export interface MarketCapFilter {
  min_market_cap_cr?: number | null;
  max_market_cap_cr?: number | null;
  require_volume_confirmation?: boolean;
}

interface MultiYearScanContextValue extends MultiYearScanState {
  startScan: (filter?: MarketCapFilter) => void;
  cancelScan: () => void;
}

const MultiYearScanContext = createContext<MultiYearScanContextValue | null>(null);

function getMultiYearWebSocketUrl(): string {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/ws/multi-year-breakout`;
}

export function MultiYearScanProvider({ children }: { children: ReactNode }) {
  const [scanning, setScanning] = useState(false);
  const [scanned, setScanned] = useState(0);
  const [total, setTotal] = useState(0);
  const [currentSymbol, setCurrentSymbol] = useState("");
  const [matches, setMatches] = useState<MultiYearMatch[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [lastScannedAt, setLastScannedAt] = useState<Date | null>(null);
  const [loadedFromDb, setLoadedFromDb] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    fetchMultiYearScanResults()
      .then((data) => {
        if (data.last_scanned_at) {
          setMatches(data.matches as MultiYearMatch[]);
          setScanned(data.scanned);
          setTotal(data.total);
          setLastScannedAt(new Date(data.last_scanned_at));
        }
      })
      .catch((err) => {
        console.error("Failed to load Multi Year scan results from DB:", err);
      })
      .finally(() => {
        setLoadedFromDb(true);
      });
  }, []);

  const closeSocket = useCallback(() => {
    const socket = wsRef.current;
    if (!socket) {
      setScanning(false);
      return;
    }
    socket.onopen = null;
    socket.onmessage = null;
    socket.onerror = null;
    socket.onclose = null;
    if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) {
      socket.close();
    }
    wsRef.current = null;
    setScanning(false);
  }, []);

  const startScan = useCallback((filter?: MarketCapFilter) => {
    closeSocket();

    setScanning(true);
    setScanned(0);
    setTotal(0);
    setCurrentSymbol("");
    setMatches([]);
    setError(null);

    const socket = new WebSocket(getMultiYearWebSocketUrl());
    wsRef.current = socket;

    socket.onopen = () => {
      socket.send(JSON.stringify({
        min_market_cap_cr: filter?.min_market_cap_cr,
        max_market_cap_cr: filter?.max_market_cap_cr,
        require_volume_confirmation: filter?.require_volume_confirmation ?? false,
      }));
    };

    socket.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === "init") {
          setTotal(msg.total);
        } else if (msg.type === "progress") {
          setScanned(msg.scanned);
          setCurrentSymbol(msg.symbol);
        } else if (msg.type === "match") {
          setMatches((prev) => [...prev, msg.data]);
        } else if (msg.type === "complete") {
          setScanning(false);
          setLastScannedAt(new Date());
          closeSocket();
        } else if (msg.type === "error") {
          setError(msg.message);
          setScanning(false);
        }
      } catch (err) {
        console.error("Error parsing WebSocket message:", err);
      }
    };

    socket.onerror = () => {
      setError("Failed to connect to scanner. Is the backend running?");
      setScanning(false);
    };

    socket.onclose = () => {
      if (wsRef.current === socket) {
        wsRef.current = null;
      }
      setScanning(false);
    };
  }, [closeSocket]);

  useEffect(() => {
    const handlePageExit = () => {
      closeSocket();
    };

    window.addEventListener("beforeunload", handlePageExit);
    window.addEventListener("pagehide", handlePageExit);

    return () => {
      window.removeEventListener("beforeunload", handlePageExit);
      window.removeEventListener("pagehide", handlePageExit);
    };
  }, [closeSocket]);

  const value = useMemo<MultiYearScanContextValue>(
    () => ({
      scanning,
      scanned,
      total,
      currentSymbol,
      matches,
      error,
      lastScannedAt,
      loadedFromDb,
      startScan,
      cancelScan: closeSocket,
    }),
    [scanning, scanned, total, currentSymbol, matches, error, lastScannedAt, loadedFromDb, startScan, closeSocket],
  );

  return <MultiYearScanContext.Provider value={value}>{children}</MultiYearScanContext.Provider>;
}

export function useMultiYearScan(): MultiYearScanContextValue {
  const ctx = useContext(MultiYearScanContext);
  if (!ctx) {
    throw new Error("useMultiYearScan must be used within MultiYearScanProvider");
  }
  return ctx;
}
