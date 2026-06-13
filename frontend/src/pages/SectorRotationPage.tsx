import { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchSectorRotation,
  triggerRotationRefresh,
  fetchIndexChart,
  type RotationSignal,
  type SectorRotationData,
  type IndexChartBar,
} from "../api";
import LightweightStockChart from "../components/LightweightStockChart";
import MultiLineChart from "../components/MultiLineChart";
import { formatIST } from "../lib/formatTime";

type Tab = "rotation" | "heatmap" | "narrative" | "charts";

const QUADRANT_META: Record<string, { label: string; color: string; bg: string }> = {
  leading: { label: "Leading", color: "#16a34a", bg: "rgba(22,163,74,0.1)" },
  weakening: { label: "Weakening", color: "#ca8a04", bg: "rgba(202,138,4,0.1)" },
  lagging: { label: "Lagging", color: "#dc2626", bg: "rgba(220,38,38,0.1)" },
  improving: { label: "Improving", color: "#2563eb", bg: "rgba(37,99,235,0.1)" },
};

const DIRECTION_ICONS: Record<string, string> = {
  accelerating: "🚀",
  turning_up: "↗️",
  turning_down: "↘️",
  decelerating: "📉",
  unknown: "➖",
};

function getHeatColor(val: number | null): string {
  if (val == null) return "var(--bg-secondary)";
  if (val >= 15) return "#14532d";
  if (val >= 10) return "#166534";
  if (val >= 5) return "#16a34a";
  if (val >= 2) return "#4ade80";
  if (val >= 0) return "#86efac";
  if (val >= -2) return "#fca5a5";
  if (val >= -5) return "#f87171";
  if (val >= -10) return "#dc2626";
  if (val >= -15) return "#991b1b";
  return "#7f1d1d";
}

function getHeatTextColor(val: number | null): string {
  if (val == null) return "var(--text-secondary)";
  if (Math.abs(val) >= 5) return "#fff";
  return "var(--text-primary)";
}

export default function SectorRotationPage() {
  const [tab, setTab] = useState<Tab>("rotation");
  const [data, setData] = useState<SectorRotationData | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const result = await fetchSectorRotation();
      setData(result);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load");
    }
  }, []);

  useEffect(() => {
    setLoading(true);
    load().finally(() => setLoading(false));
  }, [load]);

  const handleRefresh = async () => {
    setRefreshing(true);
    setError(null);
    try {
      await triggerRotationRefresh();
      // Poll for completion
      for (let i = 0; i < 90; i++) {
        await new Promise((r) => setTimeout(r, 3000));
        const result = await fetchSectorRotation();
        if (result.status === "ready" && !result._refreshing) {
          setData(result);
          break;
        }
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Refresh failed");
    } finally {
      setRefreshing(false);
      await load();
    }
  };

  const sectors = data?.sectors ?? [];
  const hasData = data?.status === "ready" && sectors.length > 0;

  return (
    <div className="sector-rotation-page">
      <div className="page-header">
        <h1>Sector Rotation</h1>
        <div className="header-actions">
          <button
            type="button"
            className="btn btn-primary btn-sm"
            onClick={handleRefresh}
            disabled={refreshing}
          >
            {refreshing ? "⟳ Computing (takes ~1 min)..." : "⟳ Refresh Analysis"}
          </button>
        </div>
      </div>

      {hasData && (
        <div className="sector-tabs">
          <button type="button" className={`sector-tab${tab === "rotation" ? " active" : ""}`} onClick={() => setTab("rotation")}>
            RRG Quadrants
          </button>
          <button type="button" className={`sector-tab${tab === "heatmap" ? " active" : ""}`} onClick={() => setTab("heatmap")}>
            Performance Heatmap
          </button>
          <button type="button" className={`sector-tab${tab === "narrative" ? " active" : ""}`} onClick={() => setTab("narrative")}>
            Insights
          </button>
          <button type="button" className={`sector-tab${tab === "charts" ? " active" : ""}`} onClick={() => setTab("charts")}>
            Index Charts
          </button>
        </div>
      )}

      {error && <div className="error-banner">{error}</div>}

      {loading ? (
        <div className="loading-state">Loading sector rotation data...</div>
      ) : !hasData ? (
        <div className="empty-state">
          {data?.message || "No analysis available."} Click "Refresh Analysis" to compute (fetches 5 years of data for 15 sectors, takes ~1 minute).
        </div>
      ) : tab === "rotation" ? (
        <RotationView data={data!} />
      ) : tab === "heatmap" ? (
        <HeatmapView sectors={sectors} />
      ) : tab === "charts" ? (
        <IndexChartsView sectors={sectors} />
      ) : (
        <NarrativeView data={data!} />
      )}

      {hasData && data?.computed_at && (
        <div className="rotation-footer">
          Analysis from: {formatIST(data.computed_at)}
          {data.duration_sec && ` · Computed in ${data.duration_sec}s`}
          {(data.failed_sectors?.length ?? 0) > 0 && ` · ${data.failed_sectors!.length} sectors unavailable`}
        </div>
      )}
    </div>
  );
}

function RotationView({ data }: { data: SectorRotationData }) {
  const sectors = data.sectors!;
  const summary = data.quadrant_summary!;

  return (
    <div className="rotation-view">
      {/* Quadrant summary */}
      <div className="rotation-summary">
        {(["leading", "improving", "weakening", "lagging"] as const).map((q) => {
          const meta = QUADRANT_META[q];
          const names = summary[q] || [];
          return (
            <div key={q} className="summary-card" style={{ background: meta.bg, borderColor: meta.color }}>
              <div className="summary-count" style={{ color: meta.color }}>{names.length}</div>
              <div className="summary-label">{meta.label}</div>
              <div className="summary-names">
                {names.map((n) => n.replace("NIFTY ", "")).join(", ") || "None"}
              </div>
            </div>
          );
        })}
      </div>

      {/* Sector cards as a list */}
      <div className="rotation-list">
        <div className="rotation-list-header">
          <span className="col-sector">Sector</span>
          <span className="col-quadrant">Quadrant</span>
          <span className="col-num">RS-Ratio</span>
          <span className="col-num">RS-Momentum</span>
          <span className="col-num">1W</span>
          <span className="col-num">1M</span>
          <span className="col-num">3M</span>
          <span className="col-num">6M</span>
          <span className="col-num">1Y</span>
          <span className="col-dir">Direction</span>
        </div>
        {sectors.map((s) => (
          <SectorRow key={s.index_name} sector={s} />
        ))}
      </div>
    </div>
  );
}

function SectorRow({ sector }: { sector: RotationSignal }) {
  const meta = QUADRANT_META[sector.rrg.quadrant] || QUADRANT_META.lagging;
  const dirIcon = DIRECTION_ICONS[sector.rrg.direction] || "➖";
  const name = sector.index_name.replace("NIFTY ", "");

  return (
    <div className="rotation-list-row">
      <span className="col-sector">
        <span className="sector-name-label">{name}</span>
        <span className="sector-price">{sector.last_close.toLocaleString("en-IN")}</span>
      </span>
      <span className="col-quadrant">
        <span className="quadrant-badge" style={{ background: meta.color }}>{meta.label}</span>
      </span>
      <span className="col-num rs-ratio">{sector.rrg.rs_ratio.toFixed(1)}</span>
      <span className="col-num rs-momentum">{sector.rrg.rs_momentum.toFixed(1)}</span>
      {(["1W", "1M", "3M", "6M", "1Y"] as const).map((tf) => {
        const val = sector.returns[tf];
        return (
          <span key={tf} className={`col-num ${val != null ? (val >= 0 ? "positive" : "negative") : ""}`}>
            {val != null ? `${val >= 0 ? "+" : ""}${val.toFixed(1)}%` : "—"}
          </span>
        );
      })}
      <span className="col-dir">{dirIcon} {sector.rrg.direction.replace("_", " ")}</span>
    </div>
  );
}

function HeatmapView({ sectors }: { sectors: RotationSignal[] }) {
  const timeframes = ["1W", "1M", "3M", "6M", "1Y", "2Y", "5Y"];

  // Sort by RS-Ratio descending
  const sorted = useMemo(
    () => [...sectors].sort((a, b) => b.rrg.rs_ratio - a.rrg.rs_ratio),
    [sectors],
  );

  return (
    <div className="heatmap-view">
      <p className="heatmap-subtitle">Absolute returns across timeframes (sorted by relative strength)</p>
      <div className="heatmap-legend">
        <span className="legend-label">-15%+</span>
        <div className="legend-bar" />
        <span className="legend-label">+15%+</span>
      </div>
      <div className="table-wrapper">
        <table className="heatmap-table">
          <thead>
            <tr>
              <th>Sector</th>
              <th className="num">RS-Ratio</th>
              {timeframes.map((tf) => (
                <th key={tf} className="num">{tf}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map((sector) => (
              <tr key={sector.index_name}>
                <td className="sector-name-cell">
                  {sector.index_name.replace("NIFTY ", "")}
                </td>
                <td className="num" style={{ fontWeight: 700 }}>{sector.rrg.rs_ratio.toFixed(1)}</td>
                {timeframes.map((tf) => {
                  const val = sector.returns[tf];
                  return (
                    <td
                      key={tf}
                      className="heatmap-cell"
                      style={{
                        background: getHeatColor(val),
                        color: getHeatTextColor(val),
                      }}
                    >
                      {val != null ? `${val >= 0 ? "+" : ""}${val.toFixed(1)}%` : "—"}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function NarrativeView({ data }: { data: SectorRotationData }) {
  const narrative = data.rotation_narrative || [];
  const sectors = data.sectors || [];
  const benchReturns = data.benchmark_returns || {};

  return (
    <div className="narrative-view">
      <div className="narrative-benchmark">
        <h3>NIFTY 50 (Benchmark)</h3>
        <div className="benchmark-returns">
          {(["1W", "1M", "3M", "6M", "1Y", "2Y", "5Y"] as const).map((tf) => {
            const val = benchReturns[tf];
            return (
              <div key={tf} className="bench-return-cell">
                <span className="bench-tf">{tf}</span>
                <span className={`bench-val ${val != null ? (val >= 0 ? "positive" : "negative") : ""}`}>
                  {val != null ? `${val >= 0 ? "+" : ""}${val.toFixed(1)}%` : "—"}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      <div className="narrative-insights">
        <h3>Rotation Insights</h3>
        {narrative.length === 0 ? (
          <p className="no-insights">No insights available.</p>
        ) : (
          <ul className="insights-list">
            {narrative.map((insight, i) => (
              <li key={i}>{insight}</li>
            ))}
          </ul>
        )}
      </div>

      <div className="narrative-relative">
        <h3>Relative Performance vs NIFTY 50 (1M)</h3>
        <div className="relative-bars">
          {[...sectors]
            .filter((s) => s.relative_returns["1M"] != null)
            .sort((a, b) => (b.relative_returns["1M"] ?? 0) - (a.relative_returns["1M"] ?? 0))
            .map((s) => {
              const val = s.relative_returns["1M"]!;
              const width = Math.min(Math.abs(val) * 4, 100);
              return (
                <div key={s.index_name} className="relative-bar-row">
                  <span className="bar-label">{s.index_name.replace("NIFTY ", "")}</span>
                  <div className="bar-container">
                    <div
                      className={`bar-fill ${val >= 0 ? "positive" : "negative"}`}
                      style={{ width: `${width}%` }}
                    />
                  </div>
                  <span className={`bar-value ${val >= 0 ? "positive" : "negative"}`}>
                    {val >= 0 ? "+" : ""}{val.toFixed(1)}%
                  </span>
                </div>
              );
            })}
        </div>
      </div>
    </div>
  );
}

const CHART_PERIODS = ["1mo", "3mo", "6mo", "1y", "2y", "5y"] as const;

const INDEX_COLORS = [
  "#2563eb", "#16a34a", "#dc2626", "#ca8a04", "#9333ea",
  "#0891b2", "#e11d48", "#65a30d", "#c026d3", "#ea580c",
  "#4f46e5", "#059669", "#be123c", "#a16207", "#7c3aed",
  "#0d9488",
];

type ChartMode = "line" | "candle";

const EXTRA_INDICES = [
  "SENSEX", "NIFTY NEXT 50", "NIFTY 100", "NIFTY 200",
  "NIFTY MIDCAP 50", "NIFTY MIDCAP 100", "NIFTY MIDCAP 150", "NIFTY PRIVATE BANK",
];

function IndexChartsView({ sectors }: { sectors: RotationSignal[] }) {
  const allIndices = ["NIFTY 50", ...sectors.map((s) => s.index_name), ...EXTRA_INDICES];
  const [selected, setSelected] = useState<string[]>(["NIFTY 50", "NIFTY IT", "NIFTY BANK"]);
  const [period, setPeriod] = useState<string>("1y");
  const [chartMode, setChartMode] = useState<ChartMode>("line");
  const [chartData, setChartData] = useState<Record<string, IndexChartBar[]>>({});
  const [loading, setLoading] = useState<string | null>(null);
  const [fullscreen, setFullscreen] = useState(false);

  const handleToggle = (name: string) => {
    setSelected((prev) =>
      prev.includes(name) ? prev.filter((n) => n !== name) : [...prev, name],
    );
  };

  const handleSelectAll = () => setSelected([...allIndices]);
  const handleClearAll = () => setSelected([]);

  useEffect(() => {
    let cancelled = false;
    const toFetch = selected.filter((name) => !chartData[`${name}__${period}`]);

    if (toFetch.length === 0) return;

    const fetchAll = async () => {
      for (const name of toFetch) {
        if (cancelled) break;
        setLoading(name);
        try {
          const res = await fetchIndexChart(name, period);
          if (!cancelled && res.bars?.length) {
            setChartData((prev) => ({ ...prev, [`${name}__${period}`]: res.bars }));
          }
        } catch {
          // skip
        }
      }
      if (!cancelled) setLoading(null);
    };
    fetchAll();
    return () => { cancelled = true; };
  }, [selected, period]);

  // Build line series data (normalized to % change from first value)
  const multiLineSeries = useMemo(() => {
    if (chartMode !== "line") return [];
    let num = 0;
    return selected
      .map((name, idx) => {
        const bars = chartData[`${name}__${period}`];
        if (!bars?.length) return null;
        const baseClose = bars[0].close;
        if (baseClose === 0) return null;
        num++;
        return {
          id: `${num}. ${name.replace("NIFTY ", "")}`,
          color: INDEX_COLORS[idx % INDEX_COLORS.length],
          lineWidth: 2,
          num,
          originalName: name,
          data: bars.map((b) => ({
            time: b.time,
            value: parseFloat((((b.close - baseClose) / baseClose) * 100).toFixed(2)),
          })),
        };
      })
      .filter(Boolean) as { id: string; color: string; lineWidth: number; num: number; originalName: string; data: { time: string; value: number }[] }[];
  }, [selected, period, chartData, chartMode]);

  // For candlestick mode, use first selected index
  const candleBars = useMemo(() => {
    if (chartMode !== "candle" || selected.length === 0) return [];
    const bars = chartData[`${selected[0]}__${period}`];
    return bars ?? [];
  }, [selected, period, chartData, chartMode]);

  // Map selected index name -> number for chip display
  const selectedNumMap = useMemo(() => {
    const map: Record<string, number> = {};
    let num = 0;
    for (const name of selected) {
      const bars = chartData[`${name}__${period}`];
      if (bars?.length) {
        num++;
        map[name] = num;
      }
    }
    return map;
  }, [selected, period, chartData]);

  return (
    <div className={`charts-view${fullscreen ? " charts-fullscreen" : ""}`}>
      <div className="charts-controls">
        <div className="charts-top-row">
          <div className="charts-mode-select">
            <button
              type="button"
              className={`mode-btn${chartMode === "line" ? " active" : ""}`}
              onClick={() => setChartMode("line")}
            >
              Line (% Change)
            </button>
            <button
              type="button"
              className={`mode-btn${chartMode === "candle" ? " active" : ""}`}
              onClick={() => setChartMode("candle")}
            >
              Candlestick
            </button>
          </div>
          <div className="charts-period-select">
            {CHART_PERIODS.map((p) => (
              <button
                key={p}
                type="button"
                className={`period-btn${period === p ? " active" : ""}`}
                onClick={() => setPeriod(p)}
              >
                {p.toUpperCase()}
              </button>
            ))}
          </div>
          <button
            type="button"
            className="fullscreen-btn"
            onClick={() => setFullscreen((f) => !f)}
            title={fullscreen ? "Exit full page" : "Full page chart"}
          >
            {fullscreen ? "✕ Exit" : "⛶ Full Page"}
          </button>
        </div>
        <div className="charts-index-selector">
          <button type="button" className="chip-action-btn" onClick={handleSelectAll}>Select All</button>
          <button type="button" className="chip-action-btn clear" onClick={handleClearAll}>Clear</button>
          <span className="chip-divider" />
          {allIndices.map((name) => {
            const isActive = selected.includes(name);
            const colorIdx = selected.indexOf(name);
            const chipColor = isActive && chartMode === "line" ? INDEX_COLORS[colorIdx % INDEX_COLORS.length] : undefined;
            const chipNum = selectedNumMap[name];
            return (
              <label
                key={name}
                className={`index-chip${isActive ? " active" : ""}`}
                style={chipColor ? { borderColor: chipColor, color: chipColor, background: `${chipColor}18` } : undefined}
              >
                <input
                  type="checkbox"
                  checked={isActive}
                  onChange={() => handleToggle(name)}
                />
                {chipNum != null && <span className="chip-num" style={{ background: chipColor }}>{chipNum}</span>}
                {name.replace("NIFTY ", "")}
              </label>
            );
          })}
        </div>
      </div>

      {loading && <div className="chart-loading">Loading {loading}...</div>}

      {chartMode === "candle" && selected.length > 1 && (
        <div className="chart-hint">Candlestick mode shows the first selected index: <strong>{selected[0]?.replace("NIFTY ", "")}</strong></div>
      )}

      <div className="chart-single-panel">
        {chartMode === "line" && multiLineSeries.length > 0 ? (
          <>
            <MultiLineChart series={multiLineSeries} height={fullscreen ? window.innerHeight - 220 : 480} />
            <div className="chart-legend-numbered">
              {multiLineSeries.map((ls) => (
                <span key={ls.id} className="legend-item-num" style={{ color: ls.color }}>
                  <span className="legend-num" style={{ background: ls.color }}>{ls.num}</span>
                  {ls.originalName.replace("NIFTY ", "")}
                </span>
              ))}
            </div>
          </>
        ) : chartMode === "candle" && candleBars.length > 0 ? (
          <LightweightStockChart bars={candleBars} height={fullscreen ? window.innerHeight - 220 : 480} />
        ) : (
          <div className="empty-state">
            {selected.length === 0 ? "Select indices above to view chart." : "Loading chart data..."}
          </div>
        )}
      </div>
    </div>
  );
}
