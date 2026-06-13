import { useCallback, useMemo, useState } from "react";
import { fetchScan } from "../../api";
import type { StockSignal } from "../../types";
import { tradingViewChartUrl, displaySymbol } from "../../utils/tradingView";
import { useLiveRefresh } from "../../hooks/useLiveRefresh";
import { freshQuote, useLiveTicks, useWatchSymbols } from "../../context/LiveTicksContext";
import TimestampLabel from "../TimestampLabel";

interface Props {
  size: "sm" | "md" | "lg";
}

interface TodayQuote {
  ltp: number;
  prev_close: number | null;
  change_pct: number | null;
}

const LIMIT_MAP = { sm: 5, md: 8, lg: 15 };

export default function BullishStocksWidget({ size }: Props) {
  const [stocks, setStocks] = useState<StockSignal[]>([]);
  const [quotes, setQuotes] = useState<Record<string, TodayQuote>>({});
  const [live, setLive] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [fetchedAt, setFetchedAt] = useState<Date | null>(null);
  const [scannedAt, setScannedAt] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const d = await fetchScan(4, "nifty50");
      const top = d.results.slice(0, LIMIT_MAP[size]);
      setStocks(top);
      setScannedAt(d.scanned_at ?? null);
      setFetchedAt(new Date());
      setError(null);

      // Overlay today's LTP + % (Upstox) on the scan's signal list
      try {
        const syms = top.map((s: StockSignal) => s.symbol).join(",");
        const res = await fetch(`/api/quotes/today?symbols=${encodeURIComponent(syms)}`);
        if (res.ok) {
          const body = await res.json();
          if (body.basis === "today") {
            setQuotes(body.quotes ?? {});
            setLive(true);
          }
        }
      } catch {
        /* scan values remain */
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [size]);
  useLiveRefresh(load, { liveMs: 5 * 60_000, closedMs: 15 * 60_000 });

  // Stream the displayed symbols; /quotes/today gives the true prev_close,
  // so the live % is exact.
  const symbols = useMemo(() => stocks.map((s) => s.symbol), [stocks]);
  useWatchSymbols(symbols);
  const { quotes: tickQuotes } = useLiveTicks();

  if (loading) return <div className="widget-loading">Loading…</div>;
  if (error) return <div className="widget-error">{error}</div>;
  if (!stocks.length) return <div className="widget-empty">No bullish signals found</div>;

  return (
    <div className="mini-list">
      {stocks.map((s) => {
        const q = quotes[s.symbol];
        const tick = freshQuote(tickQuotes, s.symbol);
        const price = tick?.price ?? q?.ltp ?? s.price;
        let pct = q?.change_pct ?? s.change_5d_pct;
        if (tick && q?.prev_close && q.prev_close > 0) {
          pct = Math.round(((tick.price - q.prev_close) / q.prev_close) * 10000) / 100;
        }
        return (
          <div key={s.symbol} className="mini-row">
            <a
              href={tradingViewChartUrl(s.symbol)}
              target="_blank"
              rel="noopener noreferrer"
              className="mini-symbol symbol-link"
            >
              {displaySymbol(s.symbol)}
            </a>
            <span className="mini-price">₹{price.toLocaleString()}</span>
            <span className={`mini-chg ${pct != null && pct >= 0 ? "pct-pos" : "pct-neg"}`}>
              {pct != null ? `${pct > 0 ? "+" : ""}${pct.toFixed(1)}%` : "—"}
            </span>
          </div>
        );
      })}
      <div className="widget-as-of">
        <TimestampLabel at={scannedAt ?? fetchedAt} label={scannedAt ? "Scanned" : "Fetched"} />
        <span className="widget-as-of-note">
          {" "}
          · {live ? "price & % are today's (live)" : "% is 5-day change"}
        </span>
      </div>
    </div>
  );
}
