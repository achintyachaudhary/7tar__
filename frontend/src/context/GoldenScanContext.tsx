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
import { fetchGoldenScanResults } from "../api";
import type { GoldenStockMatch } from "../types/golden";

interface GoldenScanState {
  scanning: boolean;
  scanned: number;
  total: number;
  currentSymbol: string;
  matches: GoldenStockMatch[];
  error: string | null;
  lastScannedAt: Date | null;
}

export interface MarketCapFilter {
  min_market_cap_cr?: number | null;
  max_market_cap_cr?: number | null;
}

interface GoldenScanContextValue extends GoldenScanState {
  startScan: (filter?: MarketCapFilter) => void;
  cancelScan: () => void;
}

const GoldenScanContext = createContext<GoldenScanContextValue | null>(null);

function getGoldenWebSocketUrl(): string {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/ws/golden-stocks`;
}

export function GoldenScanProvider({ children }: { children: ReactNode }) {
  const [scanning, setScanning] = useState(false);
  const [scanned, setScanned] = useState(0);
  const [total, setTotal] = useState(0);
  const [currentSymbol, setCurrentSymbol] = useState("");
  const [matches, setMatches] = useState<GoldenStockMatch[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [lastScannedAt, setLastScannedAt] = useState<Date | null>(null);

  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    fetchGoldenScanResults()
      .then((data) => {
        if (data.last_scanned_at) {
          setMatches(data.matches);
          setScanned(data.scanned);
          setTotal(data.total);
          setLastScannedAt(new Date(data.last_scanned_at));
        }
      })
      .catch((err) => {
        console.error("Failed to load Golden scan results:", err);
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

  const startScan = useCallback(
    (filter?: MarketCapFilter) => {
      closeSocket();

      setScanning(true);
      setScanned(0);
      setTotal(0);
      setCurrentSymbol("");
      setMatches([]);
      setError(null);

      const socket = new WebSocket(getGoldenWebSocketUrl());
      wsRef.current = socket;

      socket.onopen = () => {
        socket.send(
          JSON.stringify({
            min_market_cap_cr: filter?.min_market_cap_cr,
            max_market_cap_cr: filter?.max_market_cap_cr,
          }),
        );
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
          console.error("Error parsing Golden WebSocket message:", err);
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
    },
    [closeSocket],
  );

  useEffect(() => {
    const handlePageExit = () => closeSocket();
    window.addEventListener("beforeunload", handlePageExit);
    window.addEventListener("pagehide", handlePageExit);
    return () => {
      window.removeEventListener("beforeunload", handlePageExit);
      window.removeEventListener("pagehide", handlePageExit);
    };
  }, [closeSocket]);

  const value = useMemo<GoldenScanContextValue>(
    () => ({
      scanning,
      scanned,
      total,
      currentSymbol,
      matches,
      error,
      lastScannedAt,
      startScan,
      cancelScan: closeSocket,
    }),
    [scanning, scanned, total, currentSymbol, matches, error, lastScannedAt, startScan, closeSocket],
  );

  return <GoldenScanContext.Provider value={value}>{children}</GoldenScanContext.Provider>;
}

export function useGoldenScan(): GoldenScanContextValue {
  const ctx = useContext(GoldenScanContext);
  if (!ctx) {
    throw new Error("useGoldenScan must be used within GoldenScanProvider");
  }
  return ctx;
}
