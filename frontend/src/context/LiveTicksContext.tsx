import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useAppSocket } from "./AppSocketContext";

/** Shared consumer of the live:ticks websocket stream (~3s Upstox LTPs).
 *
 * One subscription feeds every widget: equity quotes (symbol-keyed), header
 * indices (nifty/banknifty/sensex with day change) and pulse/sector indices
 * (label-keyed, price only — widgets derive % from their REST baseline).
 *
 * Widgets that display arbitrary symbols register them with useWatchSymbols —
 * the backend adds them to the stream for a TTL window.
 */

export interface LiveQuote {
  price: number;
  ts: number; // ms epoch
}

export interface LiveIndexTick {
  price: number;
  change_abs: number | null;
  change_pct: number | null;
  ts: number;
}

// A streamed quote older than this no longer overrides REST/engine data —
// covers the feed dying mid-session without the UI freezing on a stale price.
export const QUOTE_FRESH_MS = 60_000;

// Re-register displayed symbols well inside the backend's 120s watch TTL.
const WATCH_RESEND_MS = 45_000;

interface LiveTicksContextValue {
  quotes: Record<string, LiveQuote>;
  indices: Record<string, LiveIndexTick>;
  pulse: Record<string, LiveQuote>;
  watchSymbols: (symbols: string[]) => void;
}

const LiveTicksContext = createContext<LiveTicksContextValue | null>(null);

/** Fresh streamed quote for a symbol; tolerates ".NS"-suffix mismatches. */
export function freshQuote(
  quotes: Record<string, LiveQuote>,
  symbol: string,
): LiveQuote | null {
  const q =
    quotes[symbol] ??
    quotes[`${symbol}.NS`] ??
    (symbol.endsWith(".NS") ? quotes[symbol.slice(0, -3)] : undefined);
  if (!q || Date.now() - q.ts > QUOTE_FRESH_MS) return null;
  return q;
}

/** Day-% at a live price, given a REST baseline price and its day-%.
 *  Derives the previous close the baseline was computed against. */
export function livePct(
  livePrice: number,
  basePrice: number | null | undefined,
  basePct: number | null | undefined,
): number | null {
  if (basePrice == null || basePct == null) return null;
  const prevClose = basePrice / (1 + basePct / 100);
  if (!Number.isFinite(prevClose) || prevClose <= 0) return null;
  return Math.round(((livePrice - prevClose) / prevClose) * 10000) / 100;
}

export function LiveTicksProvider({ children }: { children: ReactNode }) {
  const { subscribe, sendMessage, connected } = useAppSocket();
  const [quotes, setQuotes] = useState<Record<string, LiveQuote>>({});
  const [indices, setIndices] = useState<Record<string, LiveIndexTick>>({});
  const [pulse, setPulse] = useState<Record<string, LiveQuote>>({});

  useEffect(() => {
    return subscribe("live:ticks", (msg) => {
      const tsRaw = (msg as any).ts;
      const ts = typeof tsRaw === "number" ? tsRaw * 1000 : Date.now();

      const q = (msg as any).quotes as Record<string, number> | undefined;
      if (q && Object.keys(q).length > 0) {
        setQuotes((prev) => {
          const next = { ...prev };
          for (const [symbol, price] of Object.entries(q)) {
            if (typeof price === "number" && price > 0) next[symbol] = { price, ts };
          }
          return next;
        });
      }

      const idx = (msg as any).indices as
        | Record<string, { price: number; change_abs: number | null; change_pct: number | null }>
        | undefined;
      if (idx && Object.keys(idx).length > 0) {
        setIndices((prev) => {
          const next = { ...prev };
          for (const [id, tick] of Object.entries(idx)) {
            if (tick && typeof tick.price === "number" && tick.price > 0) {
              next[id] = { ...tick, ts };
            }
          }
          return next;
        });
      }

      const p = (msg as any).pulse as Record<string, number> | undefined;
      if (p && Object.keys(p).length > 0) {
        setPulse((prev) => {
          const next = { ...prev };
          for (const [label, price] of Object.entries(p)) {
            if (typeof price === "number" && price > 0) next[label] = { price, ts };
          }
          return next;
        });
      }
    });
  }, [subscribe]);

  const value = useMemo<LiveTicksContextValue>(
    () => ({
      quotes,
      indices,
      pulse,
      watchSymbols: (symbols: string[]) => {
        if (symbols.length > 0) sendMessage("live:watch", { symbols });
      },
    }),
    [quotes, indices, pulse, sendMessage],
  );

  // connected is intentionally part of the provider so useWatchSymbols
  // re-registers after a socket reconnect (see hook below).
  void connected;

  return <LiveTicksContext.Provider value={value}>{children}</LiveTicksContext.Provider>;
}

export function useLiveTicks(): LiveTicksContextValue {
  const ctx = useContext(LiveTicksContext);
  if (!ctx) throw new Error("useLiveTicks must be used within LiveTicksProvider");
  return ctx;
}

/** Keep the given symbols registered in the live tick stream while mounted. */
export function useWatchSymbols(symbols: string[]): void {
  const { watchSymbols } = useLiveTicks();
  const { connected } = useAppSocket();
  const key = symbols.join(",");

  useEffect(() => {
    if (!key) return;
    const syms = key.split(",");
    watchSymbols(syms);
    const id = window.setInterval(() => watchSymbols(syms), WATCH_RESEND_MS);
    return () => window.clearInterval(id);
    // re-register on reconnect: `connected` flips false→true
  }, [key, watchSymbols, connected]);
}
