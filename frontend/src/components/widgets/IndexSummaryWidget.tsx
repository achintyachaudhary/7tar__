import { useCallback, useMemo, useState } from "react";
import { fetchIndexSummary } from "../../api";
import { useLiveRefresh } from "../../hooks/useLiveRefresh";
import { QUOTE_FRESH_MS, livePct, useLiveTicks } from "../../context/LiveTicksContext";
import TimestampLabel from "../TimestampLabel";

interface IndexEntry {
  name: string;
  value: number;
  change_pct: number;
}

// Widget display name → live:ticks index id
const INDEX_TICK_IDS: Record<string, string> = {
  NIFTY: "nifty",
  BANKNIFTY: "banknifty",
  SENSEX: "sensex",
};

export default function IndexSummaryWidget() {
  const [restIndices, setRestIndices] = useState<IndexEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [fetchedAt, setFetchedAt] = useState<Date | null>(null);
  const { indices: liveIndices } = useLiveTicks();

  const load = useCallback(async () => {
    try {
      const d = await fetchIndexSummary();
      if (d && (d as { pending?: boolean }).pending) {
        window.setTimeout(() => void load(), 2500);
        return;
      }
      setRestIndices(d.indices ?? []);
      setFetchedAt(new Date());
      setError(null);
      setLoading(false);
    } catch (e) {
      setError(String(e));
      setLoading(false);
    }
  }, []);
  useLiveRefresh(load);

  // Streamed index ticks (~3s) overlay the cached REST values.
  const indices = useMemo(() => {
    return restIndices.map((idx) => {
      const tick = liveIndices[INDEX_TICK_IDS[idx.name] ?? ""];
      if (!tick || Date.now() - tick.ts > QUOTE_FRESH_MS) return idx;
      return {
        ...idx,
        value: tick.price,
        change_pct:
          tick.change_pct ?? livePct(tick.price, idx.value, idx.change_pct) ?? idx.change_pct,
      };
    });
  }, [restIndices, liveIndices]);

  if (loading) return <div className="widget-loading">Loading…</div>;
  if (error) return <div className="widget-error">{error}</div>;
  if (!indices.length) return <div className="widget-empty">No index data</div>;

  return (
    <div className="index-summary-list">
      {indices.map((idx) => (
        <div key={idx.name} className="index-row">
          <span className="index-name">{idx.name}</span>
          <span className="index-value">{idx.value.toLocaleString()}</span>
          <span className={`index-chg ${idx.change_pct >= 0 ? "pct-pos" : "pct-neg"}`}>
            {idx.change_pct > 0 ? "+" : ""}
            {idx.change_pct.toFixed(2)}%
          </span>
        </div>
      ))}
      <div className="widget-as-of">
        <TimestampLabel at={fetchedAt} label="Fetched" />
      </div>
    </div>
  );
}
