import { useEffect, useRef } from "react";
import {
  ColorType,
  createChart,
  createSeriesMarkers,
  LineSeries,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type SeriesMarker,
  type Time,
} from "lightweight-charts";
import { getChartColors, watchTheme } from "../lib/chartTheme";

export interface MultiLineSeries {
  id: string;
  color: string;
  lineWidth?: number;
  num?: number;
  data: { time: string; value: number }[];
}

interface MultiLineChartProps {
  series: MultiLineSeries[];
  height?: number;
}

const MARKER_INTERVAL_RATIO = 0.2; // place a number marker every ~20% of the data

export default function MultiLineChart({ series, height = 480 }: MultiLineChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesMapRef = useRef<Map<string, ISeriesApi<"Line">>>(new Map());
  const markersMapRef = useRef<Map<string, ISeriesMarkersPluginApi<Time>>>(new Map());

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
      crosshair: {
        horzLine: { labelVisible: true },
        vertLine: { labelVisible: true },
      },
    });

    chartRef.current = chart;

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
    });

    return () => {
      stopThemeWatch();
      ro.disconnect();
      for (const mp of markersMapRef.current.values()) {
        mp.detach();
      }
      markersMapRef.current.clear();
      chart.remove();
      chartRef.current = null;
      seriesMapRef.current.clear();
    };
  }, [height]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    const existing = seriesMapRef.current;
    const existingMarkers = markersMapRef.current;
    const incomingIds = new Set(series.map((s) => s.id));

    for (const [id, s] of existing.entries()) {
      if (!incomingIds.has(id)) {
        const mp = existingMarkers.get(id);
        if (mp) { mp.detach(); existingMarkers.delete(id); }
        chart.removeSeries(s);
        existing.delete(id);
      }
    }

    for (const spec of series) {
      let s = existing.get(spec.id);
      if (!s) {
        s = chart.addSeries(LineSeries, {
          color: spec.color,
          lineWidth: (spec.lineWidth ?? 2) as 1 | 2 | 3 | 4,
          priceLineVisible: false,
          lastValueVisible: true,
          crosshairMarkerVisible: true,
        });
        existing.set(spec.id, s);
      } else {
        s.applyOptions({ color: spec.color });
      }
      s.setData(
        spec.data.map((d) => ({ time: d.time as string & number, value: d.value })),
      );

      // Add numbered markers along the line
      if (spec.num != null && spec.data.length > 5) {
        const markers = buildNumberMarkers(spec);
        let mp = existingMarkers.get(spec.id);
        if (!mp) {
          mp = createSeriesMarkers(s, markers);
          existingMarkers.set(spec.id, mp);
        } else {
          mp.setMarkers(markers);
        }
      }
    }

    chart.timeScale().fitContent();
  }, [series]);

  if (series.length === 0) {
    return (
      <div className="chart-empty" style={{ height }}>
        Select indices to compare.
      </div>
    );
  }

  return <div ref={containerRef} className="lw-chart-container" style={{ height, width: "100%" }} />;
}

function buildNumberMarkers(spec: MultiLineSeries): SeriesMarker<Time>[] {
  const { data, num, color } = spec;
  if (!num || data.length < 10) return [];

  const markers: SeriesMarker<Time>[] = [];
  const interval = Math.max(Math.floor(data.length * MARKER_INTERVAL_RATIO), 10);

  // Place markers at 20%, 40%, 60%, 80% of the data (stagger by line number to avoid overlap)
  const offset = (num * 3) % interval;
  for (let i = offset; i < data.length - 5; i += interval) {
    markers.push({
      time: data[i].time as Time,
      position: "inBar",
      shape: "circle",
      color: color,
      size: 0.5,
      text: String(num),
    });
  }

  return markers;
}
