import { useEffect, useMemo, useState } from "react";
import { fetchDayScanChart } from "../api";
import type { OhlcBar } from "../types/chart";
import LightweightStockChart from "./LightweightStockChart";

function fmtVolume(v: number): string {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(2)}M`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(1)}K`;
  return v.toLocaleString("en-IN");
}

function computeVolumeStats(bars: OhlcBar[]) {
  const withVol = bars.filter((b) => b.volume != null && b.volume > 0);
  if (!withVol.length) return null;

  const latest = withVol[withVol.length - 1];
  const recent = withVol.slice(-20);
  const avg20 =
    recent.reduce((sum, b) => sum + (b.volume ?? 0), 0) / recent.length;
  const ratio = avg20 > 0 ? (latest.volume ?? 0) / avg20 : null;

  return {
    latest: latest.volume ?? 0,
    avg20,
    ratio,
    date: String(latest.time),
  };
}

interface VolumePanelProps {
  symbol: string;
}

export default function VolumePanel({ symbol }: VolumePanelProps) {
  const [bars, setBars] = useState<OhlcBar[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    fetchDayScanChart(symbol, "1d")
      .then((res) => {
        if (cancelled) return;
        setBars((res.bars ?? []) as OhlcBar[]);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Failed to load volume");
        setBars([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [symbol]);

  const stats = useMemo(() => computeVolumeStats(bars), [bars]);
  const chartBars = useMemo(() => bars.slice(-120), [bars]);

  if (loading) {
    return (
      <section className="insight-panel volume-panel">
        <h3 className="panel-title">Trading volume</h3>
        <p className="panel-loading">Loading volume data…</p>
      </section>
    );
  }

  if (error || !stats) {
    return (
      <section className="insight-panel volume-panel">
        <h3 className="panel-title">Trading volume</h3>
        <p className="panel-empty">
          {error ?? "Volume data not available — sync NSE Stocks data first."}
        </p>
      </section>
    );
  }

  return (
    <section className="insight-panel volume-panel">
      <h3 className="panel-title">Trading volume</h3>

      <div className="volume-stats">
        <div className="volume-stat">
          <span className="volume-stat-label">Latest ({stats.date})</span>
          <strong className="volume-stat-value">{fmtVolume(stats.latest)}</strong>
        </div>
        <div className="volume-stat">
          <span className="volume-stat-label">20-day avg</span>
          <strong className="volume-stat-value">{fmtVolume(stats.avg20)}</strong>
        </div>
        <div className="volume-stat">
          <span className="volume-stat-label">vs 20-day avg</span>
          <strong
            className={`volume-stat-value${
              stats.ratio != null && stats.ratio >= 1.5 ? " volume-stat-high" : ""
            }`}
          >
            {stats.ratio != null ? `${stats.ratio.toFixed(2)}×` : "—"}
          </strong>
        </div>
      </div>

      <div className="volume-chart-wrap">
        <LightweightStockChart bars={chartBars} height={260} showVolume />
      </div>
    </section>
  );
}
