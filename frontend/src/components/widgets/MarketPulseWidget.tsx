import { useCallback, useMemo, useState } from "react";
import { useLiveRefresh } from "../../hooks/useLiveRefresh";
import { QUOTE_FRESH_MS, livePct, useLiveTicks } from "../../context/LiveTicksContext";

interface PulseTile {
  label: string;
  value: number | null;
  change_pct: number | null;
  spark: number[];
}

function Sparkline({ points, up }: { points: number[]; up: boolean }) {
  if (points.length < 2) return <span className="pulse-spark-empty" />;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = max - min || 1;
  const w = 84;
  const h = 26;
  const path = points
    .map((p, i) => {
      const x = (i / (points.length - 1)) * w;
      const y = h - ((p - min) / range) * (h - 4) - 2;
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <svg className="pulse-spark" viewBox={`0 0 ${w} ${h}`} width={w} height={h} aria-hidden>
      <path
        d={path}
        fill="none"
        stroke={up ? "var(--green)" : "var(--red)"}
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export default function MarketPulseWidget() {
  const [restTiles, setRestTiles] = useState<PulseTile[]>([]);
  const [loading, setLoading] = useState(true);
  const { pulse } = useLiveTicks();

  const load = useCallback(async () => {
    try {
      const res = await fetch("/api/widgets/market-pulse");
      const body = await res.json();
      if (body && body.pending) {
        window.setTimeout(() => void load(), 2500);
        return;
      }
      setRestTiles(body.tiles ?? []);
      setLoading(false);
    } catch {
      setLoading(false);
    }
  }, []);
  useLiveRefresh(load, { liveMs: 60_000, closedMs: 10 * 60_000 });

  // Streamed index LTPs (~3s) overlay the REST tiles; the REST baseline
  // (value + change %) implies the previous close, so % stays consistent.
  const tiles = useMemo(() => {
    return restTiles.map((t) => {
      const live = pulse[t.label];
      if (!live || Date.now() - live.ts > QUOTE_FRESH_MS || t.value == null) return t;
      return {
        ...t,
        value: live.price,
        change_pct: livePct(live.price, t.value, t.change_pct) ?? t.change_pct,
      };
    });
  }, [restTiles, pulse]);

  if (loading) return <div className="widget-loading">Loading market pulse…</div>;
  if (tiles.length === 0) {
    return <div className="widget-empty">Index quotes unavailable (Upstox token required).</div>;
  }

  return (
    <div className="pulse-grid">
      {tiles.map((t) => {
        const up = (t.change_pct ?? 0) >= 0;
        return (
          <div key={t.label} className="pulse-tile">
            <div className="pulse-label">{t.label}</div>
            <div className="pulse-row">
              <div>
                <div className="pulse-value">
                  {t.value != null
                    ? t.value.toLocaleString("en-IN", { minimumFractionDigits: 2 })
                    : "—"}
                </div>
                <div className={`pulse-chg ${up ? "pct-pos" : "pct-neg"}`}>
                  {t.change_pct != null
                    ? `${up ? "▲" : "▼"} ${Math.abs(t.change_pct).toFixed(2)}%`
                    : "—"}
                </div>
              </div>
              <Sparkline points={t.spark} up={up} />
            </div>
          </div>
        );
      })}
    </div>
  );
}
