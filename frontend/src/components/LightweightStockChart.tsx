import { useEffect, useRef } from "react";
import {
  CandlestickSeries,
  ColorType,
  createChart,
  createSeriesMarkers,
  HistogramSeries,
  LineSeries,
  LineStyle,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type SeriesMarker,
  type Time,
} from "lightweight-charts";
import type { OhlcBar } from "../types/chart";
import { getChartColors, watchTheme } from "../lib/chartTheme";

export interface ChartLineSeries {
  id: string;
  color: string;
  lineWidth?: number;
  data: { time: string | number; value: number }[];
}

export interface ChartPriceLine {
  price: number;
  color?: string;
  title?: string;
}

interface LightweightStockChartProps {
  bars: OhlcBar[];
  height?: number;
  markers?: SeriesMarker<Time>[];
  symbol?: string;
  showVolume?: boolean;
  lineSeries?: ChartLineSeries[];
  priceLines?: ChartPriceLine[];
}

export default function LightweightStockChart({
  bars,
  height = 420,
  markers = [],
  showVolume = false,
  lineSeries = [],
  priceLines = [],
}: LightweightStockChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const markersPluginRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const lineSeriesRef = useRef<Map<string, ISeriesApi<"Line">>>(new Map());
  const priceLinesRef = useRef<IPriceLine[]>([]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const colors = getChartColors();
    const chart = createChart(container, {
      width: container.clientWidth,
      height,
      layout: {
        background: { type: ColorType.Solid, color: colors.background },
        textColor: colors.text,
      },
      grid: {
        vertLines: { color: colors.grid },
        horzLines: { color: colors.grid },
      },
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false },
    });

    const series = chart.addSeries(CandlestickSeries, {
      upColor: colors.up,
      downColor: colors.down,
      borderUpColor: colors.up,
      borderDownColor: colors.down,
      wickUpColor: colors.up,
      wickDownColor: colors.down,
    });

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });
    chart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.82, bottom: 0 },
    });

    chartRef.current = chart;
    seriesRef.current = series;
    volumeSeriesRef.current = volumeSeries;
    markersPluginRef.current = createSeriesMarkers(series, []);

    const ro = new ResizeObserver(() => {
      chart.applyOptions({ width: container.clientWidth });
    });
    ro.observe(container);

    const stopThemeWatch = watchTheme((next) => {
      chart.applyOptions({
        layout: {
          background: { type: ColorType.Solid, color: next.background },
          textColor: next.text,
        },
        grid: {
          vertLines: { color: next.grid },
          horzLines: { color: next.grid },
        },
      });
      series.applyOptions({
        upColor: next.up,
        downColor: next.down,
        borderUpColor: next.up,
        borderDownColor: next.down,
        wickUpColor: next.up,
        wickDownColor: next.down,
      });
    });

    return () => {
      stopThemeWatch();
      ro.disconnect();
      markersPluginRef.current?.detach();
      markersPluginRef.current = null;
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
      volumeSeriesRef.current = null;
      lineSeriesRef.current.clear();
      priceLinesRef.current = [];
    };
  }, [height]);

  useEffect(() => {
    if (!seriesRef.current || !bars.length) return;
    seriesRef.current.setData(
      bars.map((b) => ({
        time: b.time as string & number,
        open: b.open,
        high: b.high,
        low: b.low,
        close: b.close,
      })),
    );

    if (volumeSeriesRef.current) {
      const hasVolume = bars.some((b) => b.volume != null);
      if (showVolume && hasVolume) {
        const { upSoft, downSoft } = getChartColors();
        volumeSeriesRef.current.setData(
          bars.map((b) => ({
            time: b.time as string & number,
            value: b.volume ?? 0,
            color: b.close >= b.open ? upSoft : downSoft,
          })),
        );
      } else {
        volumeSeriesRef.current.setData([]);
      }
    }

    chartRef.current?.timeScale().fitContent();
  }, [bars, showVolume]);

  useEffect(() => {
    markersPluginRef.current?.setMarkers(markers);
  }, [markers]);

  // Indicator overlay lines (SMA / EMA, etc.)
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    const existing = lineSeriesRef.current;
    const incomingIds = new Set(lineSeries.map((l) => l.id));

    // Remove series no longer requested.
    for (const [id, series] of existing.entries()) {
      if (!incomingIds.has(id)) {
        chart.removeSeries(series);
        existing.delete(id);
      }
    }

    // Add / update requested series.
    for (const spec of lineSeries) {
      let series = existing.get(spec.id);
      if (!series) {
        series = chart.addSeries(LineSeries, {
          color: spec.color,
          lineWidth: (spec.lineWidth ?? 2) as 1 | 2 | 3 | 4,
          priceLineVisible: false,
          lastValueVisible: false,
        });
        existing.set(spec.id, series);
      } else {
        series.applyOptions({ color: spec.color });
      }
      series.setData(
        spec.data.map((d) => ({ time: d.time as string & number, value: d.value })),
      );
    }
  }, [lineSeries]);

  // Horizontal price lines (e.g. resistance level).
  useEffect(() => {
    const series = seriesRef.current;
    if (!series) return;

    for (const pl of priceLinesRef.current) {
      series.removePriceLine(pl);
    }
    priceLinesRef.current = [];

    for (const pl of priceLines) {
      const created = series.createPriceLine({
        price: pl.price,
        color: pl.color ?? getChartColors().down,
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: pl.title ?? "",
      });
      priceLinesRef.current.push(created);
    }
  }, [priceLines, bars]);

  if (!bars.length) {
    return (
      <div className="chart-empty" style={{ height }}>
        No price data for this timeframe.
      </div>
    );
  }

  return <div ref={containerRef} className="lw-chart-container" style={{ height, width: "100%" }} />;
}
