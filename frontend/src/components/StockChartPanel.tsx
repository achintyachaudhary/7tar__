import { useCallback, useEffect, useState } from "react";
import { fetchStockChart } from "../api";
import type { ChartTimeframe, OhlcBar } from "../types/chart";
import { CHART_TIMEFRAMES } from "../types/chart";
import LightweightStockChart from "./LightweightStockChart";
import SymbolLink from "./SymbolLink";

interface StockChartPanelProps {
  symbol: string;
  yfSymbol?: string | null;
}

/**
 * In-app charts use lightweight-charts + our /chart API (yfinance).
 *
 * TradingView's free Advanced Chart embed does NOT include many NSE symbols
 * ("This symbol is only available on TradingView") — see:
 * https://www.tradingview.com/widget-docs/widgets/charts/advanced-chart/
 * Use the external link for the full TradingView site instead.
 */
export default function StockChartPanel({ symbol, yfSymbol }: StockChartPanelProps) {
  const fetchSymbol = yfSymbol || symbol;

  const [timeframe, setTimeframe] = useState<ChartTimeframe>("1M");
  const [bars, setBars] = useState<OhlcBar[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadChart = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchStockChart(fetchSymbol, timeframe);
      setBars(data.bars);
    } catch (e) {
      setBars([]);
      setError(e instanceof Error ? e.message : "Failed to load chart");
    } finally {
      setLoading(false);
    }
  }, [fetchSymbol, timeframe]);

  useEffect(() => {
    loadChart();
  }, [loadChart]);

  return (
    <section className="stock-chart-panel insight-panel">
      <div className="panel-title-row">
        <h3 className="panel-title">
          Price chart — <SymbolLink symbol={symbol} yfSymbol={yfSymbol} />
        </h3>
      </div>

      <div className="period-tabs chart-timeframe-tabs">
        {CHART_TIMEFRAMES.map((tf) => (
          <button
            key={tf}
            type="button"
            className={`period-tab${timeframe === tf ? " active" : ""}`}
            onClick={() => setTimeframe(tf)}
            disabled={loading && timeframe === tf}
          >
            {tf}
          </button>
        ))}
      </div>

      <div className="chart-frame">
        {loading ? (
          <div className="chart-empty">Loading chart…</div>
        ) : error ? (
          <div className="chart-empty chart-error">
            {error}
            <button type="button" className="refresh-btn" style={{ marginTop: "0.75rem" }} onClick={loadChart}>
              Retry
            </button>
          </div>
        ) : (
          <LightweightStockChart key={`${fetchSymbol}-${timeframe}`} bars={bars} />
        )}
      </div>

      <p className="chart-hint">
        Candlestick data from Yahoo Finance (refreshed per timeframe). Cached storage in the backend is planned.
      </p>
    </section>
  );
}
