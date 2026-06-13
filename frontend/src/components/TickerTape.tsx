import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  fetchFollowingNews,
  fetchMarketIndices,
  fetchTopMovers,
} from "../api";
import { useAppSocket } from "../context/AppSocketContext";
import { useWatchSymbols } from "../context/LiveTicksContext";
import { useLiveRefresh } from "../hooks/useLiveRefresh";
import { displaySymbol } from "../utils/tradingView";

interface TapeItem {
  id: string;
  kind: "index" | "gainer" | "loser" | "news" | "info";
  text: string;
  value?: string;
  dir?: "up" | "down";
}

interface MoverRow {
  symbol: string;
  price: number | null;
  change_5d_pct: number | null;
}

interface LiveIndexTick {
  price: number;
  change_pct: number | null;
}

const REFRESH_MS = 5 * 60 * 1000;

function fmtPct(v: number | null | undefined): string {
  if (v == null) return "";
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;
}

export default function TickerTape() {
  const [items, setItems] = useState<TapeItem[]>([]);
  const [moverSymbols, setMoverSymbols] = useState<string[]>([]);
  const liveIndices = useRef<Record<string, LiveIndexTick>>({});
  const { subscribe } = useAppSocket();
  const [, forceRender] = useState(0);

  // Keep the tape's mover symbols in the live tick stream.
  useWatchSymbols(moverSymbols);

  const load = useCallback(async () => {
    const next: TapeItem[] = [];

    const [indicesRes, moversRes, newsRes] = await Promise.allSettled([
      fetchMarketIndices(),
      fetchTopMovers(),
      fetchFollowingNews(),
    ]);

    if (indicesRes.status === "fulfilled") {
      for (const idx of indicesRes.value.indices) {
        if (idx.index_id === "sensex") continue;
        const live = liveIndices.current[idx.index_id];
        const pct = live?.change_pct ?? idx.change_pct;
        next.push({
          id: `idx-${idx.index_id}`,
          kind: "index",
          text: idx.display_name,
          value: `${(live?.price ?? idx.last_value)?.toLocaleString("en-IN", { maximumFractionDigits: 2 })} ${fmtPct(pct)}`,
          dir: (pct ?? 0) >= 0 ? "up" : "down",
        });
      }
    }

    if (moversRes.status === "fulfilled") {
      const data = moversRes.value as { gainers?: MoverRow[]; losers?: MoverRow[] };
      setMoverSymbols(
        [...(data.gainers ?? []).slice(0, 5), ...(data.losers ?? []).slice(0, 5)].map(
          (m) => m.symbol,
        ),
      );
      for (const g of (data.gainers ?? []).slice(0, 5)) {
        next.push({
          id: `g-${g.symbol}`,
          kind: "gainer",
          text: displaySymbol(g.symbol),
          value: `₹${g.price ?? "—"} ${fmtPct(g.change_5d_pct)} (5d)`,
          dir: "up",
        });
      }
      for (const l of (data.losers ?? []).slice(0, 5)) {
        next.push({
          id: `l-${l.symbol}`,
          kind: "loser",
          text: displaySymbol(l.symbol),
          value: `₹${l.price ?? "—"} ${fmtPct(l.change_5d_pct)} (5d)`,
          dir: "down",
        });
      }
    }

    if (newsRes.status === "fulfilled") {
      for (const a of newsRes.value.articles.slice(0, 6)) {
        if (!a.heading) continue;
        next.push({
          id: `n-${a.article_link ?? a.heading}`,
          kind: "news",
          text: `${displaySymbol(a.symbol)} · ${a.heading}`,
        });
      }
    }

    if (next.length === 0) {
      next.push({
        id: "empty",
        kind: "info",
        text: "Follow stocks and run scans to fill this tape with live market activity",
      });
    }
    setItems(next);
  }, []);

  useLiveRefresh(load, { liveMs: REFRESH_MS, closedMs: REFRESH_MS });

  // Live ticks update tape values in place (no remount → smooth scroll):
  // indices get price + day %, movers get the streamed LTP.
  useEffect(() => {
    const unsub = subscribe("live:ticks", (msg) => {
      const ticks = (msg.indices ?? {}) as Record<string, LiveIndexTick>;
      const quotes = (msg.quotes ?? {}) as Record<string, number>;
      if (Object.keys(ticks).length === 0 && Object.keys(quotes).length === 0) return;
      Object.assign(liveIndices.current, ticks);
      setItems((prev) =>
        prev.map((item) => {
          if (item.kind === "index") {
            const tick = ticks[item.id.replace("idx-", "")];
            if (!tick) return item;
            return {
              ...item,
              value: `${tick.price.toLocaleString("en-IN", { maximumFractionDigits: 2 })} ${fmtPct(tick.change_pct)}`,
              dir: (tick.change_pct ?? 0) >= 0 ? "up" : "down",
            };
          }
          if ((item.kind === "gainer" || item.kind === "loser") && item.value) {
            const sym = item.id.slice(2);
            const price = quotes[sym] ?? quotes[`${sym}.NS`];
            if (typeof price !== "number" || price <= 0) return item;
            return {
              ...item,
              value: item.value.replace(
                /^₹\S+/,
                `₹${price.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`,
              ),
            };
          }
          return item;
        }),
      );
      forceRender((n) => n + 1);
    });
    return unsub;
  }, [subscribe]);

  // Scroll duration scales with content so speed stays constant
  const duration = useMemo(() => Math.max(30, items.length * 6), [items.length]);

  if (items.length === 0) return null;

  const renderItems = (suffix: string) =>
    items.map((item) => (
      <span key={`${item.id}-${suffix}`} className={`tape-item tape-${item.kind}`}>
        <span className="tape-text">{item.text}</span>
        {item.value && (
          <span className={`tape-value ${item.dir === "down" ? "down" : "up"}`}>
            {item.value}
          </span>
        )}
      </span>
    ));

  return (
    <div className="ticker-tape" role="marquee" aria-label="Market activity ticker">
      <div className="ticker-tape-track" style={{ animationDuration: `${duration}s` }}>
        <div className="ticker-tape-group">{renderItems("a")}</div>
        <div className="ticker-tape-group" aria-hidden>
          {renderItems("b")}
        </div>
      </div>
    </div>
  );
}
