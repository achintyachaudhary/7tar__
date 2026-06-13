import { useCallback, useMemo, useState } from "react";
import { fetchTopMovers } from "../../api";
import { tradingViewChartUrl, displaySymbol } from "../../utils/tradingView";
import { useLiveRefresh } from "../../hooks/useLiveRefresh";
import {
  freshQuote,
  livePct,
  useLiveTicks,
  useWatchSymbols,
} from "../../context/LiveTicksContext";
import TimestampLabel from "../TimestampLabel";

interface Mover {
  symbol: string;
  price: number;
  change_5d_pct: number | null;
}

interface TopMoversData {
  gainers: Mover[];
  losers: Mover[];
}

export default function TopMoversWidget() {
  const [data, setData] = useState<TopMoversData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [fetchedAt, setFetchedAt] = useState<Date | null>(null);
  const [tab, setTab] = useState<"gainers" | "losers">("gainers");

  const load = useCallback(async () => {
    try {
      const d = await fetchTopMovers();
      if (d && (d as { pending?: boolean }).pending) {
        // Backend is computing in the background — poll until it lands
        window.setTimeout(() => void load(), 2500);
        return;
      }
      setData(d);
      setFetchedAt(new Date());
      setError(null);
      setLoading(false);
    } catch (e) {
      setError(String(e));
      setLoading(false);
    }
  }, []);
  useLiveRefresh(load);

  // Stream every displayed symbol; overlay prices from live ticks (~3s).
  const allSymbols = useMemo(
    () => (data ? [...data.gainers, ...data.losers].map((m) => m.symbol) : []),
    [data],
  );
  useWatchSymbols(allSymbols);
  const { quotes } = useLiveTicks();
  const basisToday = (data as { basis?: string } | null)?.basis === "today";

  const liveMovers = useMemo(() => {
    if (!data) return [];
    const rows = tab === "gainers" ? data.gainers : data.losers;
    return rows.map((m) => {
      const q = freshQuote(quotes, m.symbol);
      if (!q || q.price === m.price) return m;
      return {
        ...m,
        price: q.price,
        // % can only be re-marked when the baseline % is today's change.
        change_5d_pct: basisToday
          ? livePct(q.price, m.price, m.change_5d_pct) ?? m.change_5d_pct
          : m.change_5d_pct,
      };
    });
  }, [data, tab, quotes, basisToday]);

  if (loading) return <div className="widget-loading">Loading…</div>;
  if (error) return <div className="widget-error">{error}</div>;
  if (!data) return <div className="widget-empty">No data</div>;

  const movers = liveMovers;

  return (
    <div>
      <div className="widget-tabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={tab === "gainers"}
          className={`widget-tab ${tab === "gainers" ? "active up" : ""}`}
          onClick={() => setTab("gainers")}
        >
          <span className="widget-tab-dot" aria-hidden="true">▲</span>
          Gainers
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "losers"}
          className={`widget-tab ${tab === "losers" ? "active down" : ""}`}
          onClick={() => setTab("losers")}
        >
          <span className="widget-tab-dot" aria-hidden="true">▼</span>
          Losers
        </button>
      </div>
      <div className="mini-list">
        {movers.length === 0 && <div className="widget-empty">No data yet</div>}
        {movers.map((m, i) => (
          <div key={m.symbol} className="mini-row">
            <span className="mini-rank" aria-hidden="true">{i + 1}</span>
            <a
              href={tradingViewChartUrl(m.symbol)}
              target="_blank"
              rel="noopener noreferrer"
              className="mini-symbol symbol-link"
            >
              {displaySymbol(m.symbol)}
            </a>
            <span className="mini-price">₹{m.price.toLocaleString()}</span>
            <span className={`mini-chg ${(m.change_5d_pct ?? 0) >= 0 ? "pct-pos" : "pct-neg"}`}>
              {m.change_5d_pct != null
                ? `${m.change_5d_pct > 0 ? "+" : ""}${m.change_5d_pct.toFixed(1)}%`
                : "—"}
            </span>
          </div>
        ))}
      </div>
      <div className="widget-as-of">
        <TimestampLabel at={fetchedAt} label="Fetched" />
        <span className="widget-as-of-note">
          {" "}
          · {(data as { basis?: string } | null)?.basis === "today"
            ? "% is today's change (live)"
            : "% is 5-day change"}
        </span>
      </div>
    </div>
  );
}
