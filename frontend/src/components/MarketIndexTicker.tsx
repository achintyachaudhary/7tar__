import { useCallback, useEffect, useRef, useState } from "react";
import { fetchMarketIndices } from "../api";
import type { MarketIndexQuote, MarketIndicesResponse } from "../types/marketIndex";
import { formatIST } from "../lib/formatTime";
import { useNseSessionPhase } from "../lib/nseSession";
import { useAppSocket } from "../context/AppSocketContext";

// REST polling is the fallback; during the session the websocket tick feed
// (live:ticks, every ~3s) drives the numbers.
const POLL_LIVE_MS = 60 * 1000;
const POLL_CLOSED_MS = 5 * 60 * 1000;

const TICKER_INDEX_IDS = new Set(["nifty", "banknifty"]);

const TRADINGVIEW_SYMBOLS: Record<string, string> = {
  nifty: "NSE:NIFTY",
  banknifty: "NSE:BANKNIFTY",
  sensex: "BSE:SENSEX",
};

interface LiveIndexTick {
  price: number;
  change_abs: number | null;
  change_pct: number | null;
}

function tradingViewUrl(indexId: string): string {
  const symbol = TRADINGVIEW_SYMBOLS[indexId] ?? `NSE:${indexId.toUpperCase()}`;
  return `https://in.tradingview.com/chart/?symbol=${encodeURIComponent(symbol)}`;
}

function fmtValue(v: number | null): string {
  if (v == null) return "—";
  return v.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtChange(abs: number | null, pct: number | null): string {
  if (abs == null || pct == null) return "—";
  return `${abs.toFixed(2)} (${pct.toFixed(2)}%)`;
}

export default function MarketIndexTicker() {
  const [indices, setIndices] = useState<MarketIndexQuote[]>([]);
  const [marketOpen, setMarketOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [flash, setFlash] = useState<Record<string, "up" | "down" | null>>({});
  const [tickLive, setTickLive] = useState(false);
  const sessionPhase = useNseSessionPhase();
  const sessionOpen = sessionPhase !== "closed";
  const { subscribe } = useAppSocket();
  const lastTickAt = useRef(0);
  const prevPrices = useRef<Record<string, number>>({});

  const load = useCallback(async () => {
    try {
      const res: MarketIndicesResponse = await fetchMarketIndices();
      // Websocket ticks are fresher — don't let a stale REST response clobber them.
      if (Date.now() - lastTickAt.current > 10_000) {
        setIndices(res.indices.filter((i) => TICKER_INDEX_IDS.has(i.index_id)));
      }
      setMarketOpen(Boolean(res.market_open));
    } catch {
      /* keep last values */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const interval = sessionOpen ? POLL_LIVE_MS : POLL_CLOSED_MS;
    const id = window.setInterval(() => void load(), interval);
    return () => window.clearInterval(id);
  }, [load, sessionOpen]);

  // Live websocket ticks (every ~3s during the session)
  useEffect(() => {
    const unsub = subscribe("live:ticks", (msg) => {
      const ticks = (msg.indices ?? {}) as Record<string, LiveIndexTick>;
      if (!ticks || Object.keys(ticks).length === 0) return;
      lastTickAt.current = Date.now();
      setTickLive(true);
      setIndices((prev) =>
        prev.map((idx) => {
          const tick = ticks[idx.index_id];
          if (!tick) return idx;
          const prevPrice = prevPrices.current[idx.index_id];
          if (prevPrice != null && tick.price !== prevPrice) {
            const dir = tick.price > prevPrice ? "up" : "down";
            setFlash((f) => ({ ...f, [idx.index_id]: dir }));
            window.setTimeout(
              () => setFlash((f) => ({ ...f, [idx.index_id]: null })),
              700,
            );
          }
          prevPrices.current[idx.index_id] = tick.price;
          return {
            ...idx,
            last_value: tick.price,
            change_abs: tick.change_abs ?? idx.change_abs,
            change_pct: tick.change_pct ?? idx.change_pct,
          };
        }),
      );
    });
    return unsub;
  }, [subscribe]);

  // Ticks stop → drop the live indicator after 30s
  useEffect(() => {
    const id = window.setInterval(() => {
      if (Date.now() - lastTickAt.current > 30_000) setTickLive(false);
    }, 10_000);
    return () => window.clearInterval(id);
  }, []);

  if (loading && indices.length === 0) {
    return <div className="market-index-ticker loading">Loading indices…</div>;
  }

  const live = marketOpen || sessionOpen;
  const preOpen = sessionPhase === "pre_open";

  return (
    <div className="market-index-ticker" role="group" aria-label="Market indices">
      <span
        className={`market-session-pill ${live ? (preOpen ? "preopen" : "live") : "closed"}`}
        title={
          live
            ? preOpen
              ? "NSE pre-open (9:00–9:15 IST) — first prices from ~9:07, normal trading from 9:15"
              : tickLive
                ? "NSE session open — live websocket ticks every ~3s"
                : "NSE session open — quotes refresh every minute"
            : "NSE session closed — showing end-of-day values (3:30 pm IST close)"
        }
      >
        <span className="market-session-dot" aria-hidden />
        {live ? (preOpen ? "PRE-OPEN" : tickLive ? "LIVE · WS" : "LIVE") : "At close"}
      </span>
      {indices.map((idx) => {
        const positive = (idx.change_pct ?? 0) >= 0;
        const quoteAt = idx.updated_at ? formatIST(idx.updated_at) : null;
        const flashCls = flash[idx.index_id] ? ` tick-flash-${flash[idx.index_id]}` : "";
        return (
          <div key={idx.index_id} className="market-index-item">
            <a
              className="market-index-item-inner"
              href={tradingViewUrl(idx.index_id)}
              target="_blank"
              rel="noopener noreferrer"
              title={
                (live ? "Live quote" : "End-of-day close (3:30 pm IST)") +
                (quoteAt ? ` — fetched ${quoteAt}.` : ".") +
                " Open on TradingView."
              }
            >
              <span className="market-index-item-main">
                <span className="market-index-name">{idx.display_name}</span>
                <span className={`market-index-value${flashCls}`}>
                  {fmtValue(idx.last_value)}
                </span>
                <span className={`market-index-change ${positive ? "pct-pos" : "pct-neg"}`}>
                  {fmtChange(idx.change_abs, idx.change_pct)}
                </span>
              </span>
            </a>
          </div>
        );
      })}
    </div>
  );
}
