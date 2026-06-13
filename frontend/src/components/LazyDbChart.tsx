import { useEffect, useRef, useState } from "react";
import { fetchDayScanChart, type DayScanChartInterval } from "../api";
import type { SeriesMarker, Time } from "lightweight-charts";
import LightweightStockChart from "./LightweightStockChart";
import type { OhlcBar } from "../types/chart";

interface PriceLine {
  price: number;
  color: string;
  title: string;
}

interface LazyDbChartProps {
  symbol: string;
  interval?: DayScanChartInterval;
  height?: number;
  showVolume?: boolean;
  priceLines?: PriceLine[];
  markers?: SeriesMarker<Time>[];
}

export default function LazyDbChart({
  symbol,
  interval = "1d",
  height = 220,
  showVolume = false,
  priceLines,
  markers,
}: LazyDbChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  // Charts mount only when scrolled near the viewport, so screener pages can
  // render every match without firing hundreds of simultaneous requests.
  const [visible, setVisible] = useState(false);
  const [bars, setBars] = useState<OhlcBar[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el || visible) return;
    if (typeof IntersectionObserver === "undefined") {
      setVisible(true);
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { rootMargin: "400px 0px" },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [visible]);

  useEffect(() => {
    if (!visible) return;
    let cancelled = false;
    setLoading(true);
    setError(null);

    fetchDayScanChart(symbol, interval)
      .then((res) => {
        if (cancelled) return;
        setBars((res.bars ?? []) as OhlcBar[]);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Chart load failed");
        setBars([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [symbol, interval, visible]);

  if (!visible || loading) {
    return (
      <div
        ref={containerRef}
        className="lazy-db-chart lazy-db-chart-loading"
        style={{ height }}
      >
        {visible ? "Loading chart…" : ""}
      </div>
    );
  }

  if (error || bars.length === 0) {
    return (
      <div className="lazy-db-chart lazy-db-chart-empty" style={{ height }}>
        {error ?? "No chart data — run Day Scan sync first"}
      </div>
    );
  }

  return (
    <LightweightStockChart
      bars={bars}
      symbol={symbol}
      height={height}
      showVolume={showVolume}
      priceLines={priceLines}
      markers={markers}
    />
  );
}
