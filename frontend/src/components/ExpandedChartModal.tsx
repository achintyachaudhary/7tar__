import { useEffect, useMemo, useState } from "react";
import { fetchDayScanChart, type DayScanChartInterval } from "../api";
import LightweightStockChart, {
  type ChartLineSeries,
  type ChartPriceLine,
} from "./LightweightStockChart";
import SymbolLink from "./SymbolLink";
import { getChartColors } from "../lib/chartTheme";
import type { OhlcBar } from "../types/chart";

const TIMEFRAMES: { key: DayScanChartInterval; label: string }[] = [
  { key: "1d", label: "1D" },
  { key: "1wk", label: "1W" },
  { key: "1mo", label: "1M" },
];

interface IndicatorState {
  sma20: boolean;
  sma50: boolean;
  ema20: boolean;
}

const INDICATOR_META: { key: keyof IndicatorState; label: string; color: string }[] = [
  { key: "sma20", label: "SMA 20", color: "#f59e0b" },
  { key: "sma50", label: "SMA 50", color: "#3b82f6" },
  { key: "ema20", label: "EMA 20", color: "#a855f7" },
];

function sma(values: number[], period: number): (number | null)[] {
  const out: (number | null)[] = new Array(values.length).fill(null);
  let sum = 0;
  for (let i = 0; i < values.length; i++) {
    sum += values[i];
    if (i >= period) sum -= values[i - period];
    if (i >= period - 1) out[i] = sum / period;
  }
  return out;
}

function ema(values: number[], period: number): (number | null)[] {
  const out: (number | null)[] = new Array(values.length).fill(null);
  if (values.length < period) return out;
  const k = 2 / (period + 1);
  let prev = values.slice(0, period).reduce((a, b) => a + b, 0) / period;
  out[period - 1] = prev;
  for (let i = period; i < values.length; i++) {
    prev = values[i] * k + prev * (1 - k);
    out[i] = prev;
  }
  return out;
}

interface ExpandedChartModalProps {
  symbol: string;
  companyName?: string;
  subtitle?: string;
  resistance?: number | null;
  onClose: () => void;
}

export default function ExpandedChartModal({
  symbol,
  companyName,
  subtitle,
  resistance,
  onClose,
}: ExpandedChartModalProps) {
  const [chartInterval, setChartInterval] = useState<DayScanChartInterval>("1d");
  const [bars, setBars] = useState<OhlcBar[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [indicators, setIndicators] = useState<IndicatorState>({
    sma20: true,
    sma50: false,
    ema20: false,
  });

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchDayScanChart(symbol, chartInterval)
      .then((data) => {
        if (!cancelled) setBars(data.bars);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load chart");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [symbol, chartInterval]);

  const lineSeries = useMemo<ChartLineSeries[]>(() => {
    if (!bars.length) return [];
    const closes = bars.map((b) => b.close);
    const times = bars.map((b) => b.time);
    const build = (vals: (number | null)[], color: string, id: string): ChartLineSeries => ({
      id,
      color,
      data: vals
        .map((v, i) => (v == null ? null : { time: times[i], value: v }))
        .filter((d): d is { time: string | number; value: number } => d !== null),
    });
    const out: ChartLineSeries[] = [];
    if (indicators.sma20) out.push(build(sma(closes, 20), "#f59e0b", "SMA 20"));
    if (indicators.sma50) out.push(build(sma(closes, 50), "#3b82f6", "SMA 50"));
    if (indicators.ema20) out.push(build(ema(closes, 20), "#a855f7", "EMA 20"));
    return out;
  }, [bars, indicators]);

  const priceLines = useMemo<ChartPriceLine[]>(
    () =>
      resistance
        ? [{ price: resistance, color: getChartColors().down, title: "Resistance" }]
        : [],
    [resistance],
  );

  return (
    <div className="expanded-chart-overlay" onClick={onClose}>
      <div className="expanded-chart-modal" onClick={(e) => e.stopPropagation()}>
        <div className="expanded-chart-header">
          <div>
            <h2>
              <SymbolLink symbol={symbol} onClick={(e) => e.stopPropagation()} />
              {companyName ? ` — ${companyName}` : ""}
            </h2>
            {subtitle && <p className="meta">{subtitle}</p>}
          </div>
          <div className="expanded-chart-header-actions">
            <button type="button" className="expanded-chart-close" onClick={onClose} aria-label="Close">
              ✕
            </button>
          </div>
        </div>

        <div className="expanded-chart-controls">
          <div className="expanded-chart-tf">
            {TIMEFRAMES.map((tf) => (
              <button
                key={tf.key}
                type="button"
                className={`expanded-chart-tf-btn${chartInterval === tf.key ? " active" : ""}`}
                onClick={() => setChartInterval(tf.key)}
              >
                {tf.label}
              </button>
            ))}
          </div>
          <div className="expanded-chart-indicators">
            <span className="expanded-chart-indicators-label">Indicators:</span>
            {INDICATOR_META.map((ind) => (
              <label key={ind.key} className="expanded-chart-indicator">
                <input
                  type="checkbox"
                  checked={indicators[ind.key]}
                  onChange={(e) =>
                    setIndicators((prev) => ({ ...prev, [ind.key]: e.target.checked }))
                  }
                />
                <span style={{ color: ind.color, fontWeight: 600 }}>{ind.label}</span>
              </label>
            ))}
          </div>
        </div>

        <div className="expanded-chart-body">
          {loading && <div className="status loading">Loading chart…</div>}
          {error && !loading && <div className="status error">{error}</div>}
          {!loading && !error && (
            <LightweightStockChart
              bars={bars}
              height={520}
              lineSeries={lineSeries}
              priceLines={priceLines}
            />
          )}
        </div>
      </div>
    </div>
  );
}
