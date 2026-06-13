import { useEffect, useState } from "react";
import { fetchDayScanChart } from "../api";
import LightweightStockChart from "./LightweightStockChart";
import SymbolLink from "./SymbolLink";
import type { DayScanRow } from "../types/dayScan";
import type { OhlcBar } from "../types/chart";

interface DayScanChartModalProps {
  stock: DayScanRow;
  onClose: () => void;
}

export default function DayScanChartModal({ stock, onClose }: DayScanChartModalProps) {
  const [bars, setBars] = useState<OhlcBar[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [meta, setMeta] = useState<{ from: string | null; to: string | null; count: number }>({
    from: null,
    to: null,
    count: 0,
  });

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    fetchDayScanChart(stock.symbol)
      .then((data) => {
        if (cancelled) return;
        setBars(data.bars);
        setMeta({
          from: data.from_date,
          to: data.to_date,
          count: data.bar_count,
        });
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Failed to load chart");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [stock.symbol]);

  return (
    <div className="day-scan-chart-overlay" onClick={onClose}>
      <div className="day-scan-chart-modal" onClick={(e) => e.stopPropagation()}>
        <div className="day-scan-chart-header">
          <div>
            <h2>
              <SymbolLink
                symbol={stock.symbol}
                onClick={(e) => e.stopPropagation()}
              />{" "}
              — {stock.company_name}
            </h2>
            <p className="meta">
              {meta.count > 0
                ? `${meta.count} daily bars · ${meta.from} → ${meta.to} (all stored data)`
                : "Loading stored price history…"}
            </p>
          </div>
          <div className="day-scan-chart-header-actions">
            <button type="button" className="day-scan-chart-close" onClick={onClose} aria-label="Close">
              ✕
            </button>
          </div>
        </div>

        <div className="day-scan-chart-body">
          {loading && <div className="status loading">Loading chart from database…</div>}
          {error && !loading && <div className="status error">{error}</div>}
          {!loading && !error && <LightweightStockChart bars={bars} height={520} />}
        </div>

        <div className="day-scan-chart-footer">
          <div className="day-scan-chart-stats">
            {stock.last_price != null && <span>Last: ₹{stock.last_price}</span>}
            {stock.return_1y_pct != null && (
              <span className={stock.return_1y_pct >= 0 ? "positive" : "negative"}>
                1Y: {stock.return_1y_pct > 0 ? "+" : ""}
                {stock.return_1y_pct.toFixed(2)}%
              </span>
            )}
          </div>
          <button type="button" className="day-scan-fetch-btn" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
