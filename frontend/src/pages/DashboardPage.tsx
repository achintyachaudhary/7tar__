import { useCallback, useEffect, useState } from "react";
import {
  fetchDashboardLayout,
  saveDashboardLayout,
  type WidgetItem,
} from "../api";
import WidgetPicker from "../components/WidgetPicker";
import BullishStocksWidget from "../components/widgets/BullishStocksWidget";
import IndexSummaryWidget from "../components/widgets/IndexSummaryWidget";
import TopMoversWidget from "../components/widgets/TopMoversWidget";
import StrategySummaryWidget from "../components/widgets/StrategySummaryWidget";
import StockListsWidget from "../components/widgets/StockListsWidget";
import AlertsWidget from "../components/widgets/AlertsWidget";
import NewsWidget from "../components/widgets/NewsWidget";
import StockAiWidget from "../components/widgets/StockAiWidget";
import PulseNewsWidget from "../components/widgets/PulseNewsWidget";
import IpoRadarWidget from "../components/widgets/IpoRadarWidget";
import MarketPulseWidget from "../components/widgets/MarketPulseWidget";
import StockSymbolPicker, { type StockSymbolOption } from "../components/StockSymbolPicker";
import StockDetailModal from "../components/StockDetailModal";
import TickerTape from "../components/TickerTape";
import type { SelectedStock } from "../types";

type WidgetWithId = WidgetItem & { id?: number };

const WIDGET_LABELS: Record<string, string> = {
  bullish_stocks: "Bullish Stocks",
  recent_ipos: "IPO Radar — Open & Upcoming",
  index_summary: "Index Summary",
  top_movers: "Top Movers",
  strategy_summary: "Strategy Summary",
  stock_lists: "Watchlists",
  price_alerts: "Price Alerts",
  news: "News — Following",
  market_pulse: "Market & Sectors",
  stock_ai: "Stock AI Analyst",
  pulse_news: "Pulse News — AI Summarized",
};

const WIDGET_ICONS: Record<string, string> = {
  bullish_stocks: "📊",
  recent_ipos: "🎯",
  market_pulse: "📡",
  index_summary: "📈",
  top_movers: "⚡",
  strategy_summary: "🎯",
  stock_lists: "⭐",
  price_alerts: "🔔",
  news: "📰",
  stock_ai: "🤖",
  pulse_news: "🗞️",
};

// Curated default ordering — most actionable first
const WIDGET_ORDER = [
  "market_pulse",
  "stock_ai",
  "pulse_news",
  "news",
  "top_movers",
  "price_alerts",
  "stock_lists",
  "bullish_stocks",
  "strategy_summary",
  "recent_ipos",
  "index_summary",
];

function orderWidgets<T extends { widget_type: string }>(widgets: T[]): T[] {
  return [...widgets].sort((a, b) => {
    const ai = WIDGET_ORDER.indexOf(a.widget_type);
    const bi = WIDGET_ORDER.indexOf(b.widget_type);
    return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
  });
}

function WidgetContent({
  widget,
}: {
  widget: WidgetWithId;
}) {
  switch (widget.widget_type) {
    case "bullish_stocks":
      return <BullishStocksWidget size={widget.size} />;
    case "recent_ipos":
      return <IpoRadarWidget />;
    case "index_summary":
      return <IndexSummaryWidget />;
    case "top_movers":
      return <TopMoversWidget />;
    case "strategy_summary":
      return <StrategySummaryWidget />;
    case "stock_lists":
      return <StockListsWidget size={widget.size} />;
    case "price_alerts":
      return <AlertsWidget size={widget.size} />;
    case "news":
      return <NewsWidget size={widget.size} />;
    case "market_pulse":
      return <MarketPulseWidget />;
    case "stock_ai":
      return <StockAiWidget size={widget.size} />;
    case "pulse_news":
      return <PulseNewsWidget size={widget.size} />;
    default:
      return <div className="widget-empty">Unknown widget: {widget.widget_type}</div>;
  }
}

export default function DashboardPage() {
  const [widgets, setWidgets] = useState<WidgetWithId[]>([]);
  const [loading, setLoading] = useState(true);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [searchValue, setSearchValue] = useState<StockSymbolOption | null>(null);
  const [selectedStock, setSelectedStock] = useState<SelectedStock | null>(null);

  function openStock(option: StockSymbolOption | null) {
    if (!option) return;
    setSelectedStock({ symbol: option.symbol, label: option.company_name });
    setSearchValue(null);
  }

  useEffect(() => {
    fetchDashboardLayout()
      .then((data) => {
        let loaded = data.widgets as WidgetWithId[];
        if (!loaded.some((w) => w.widget_type === "market_pulse")) {
          loaded = [
            { widget_type: "market_pulse", size: "lg", position: 0, config: {} },
            ...loaded,
          ];
          void saveDashboardLayout(
            loaded.map((w, i) => ({
              widget_type: w.widget_type,
              size: w.size,
              position: i,
              config: w.config ?? {},
            })),
          );
        }
        if (!loaded.some((w) => w.widget_type === "price_alerts")) {
          loaded = [
            ...loaded,
            {
              widget_type: "price_alerts",
              size: "lg",
              position: loaded.length,
              config: {},
            },
          ];
          void saveDashboardLayout(
            loaded.map((w, i) => ({
              widget_type: w.widget_type,
              size: w.size,
              position: i,
              config: w.config ?? {},
            })),
          );
        }
        for (const autoType of ["stock_ai", "pulse_news"] as const) {
          if (!loaded.some((w) => w.widget_type === autoType)) {
            loaded = [
              ...loaded,
              {
                widget_type: autoType,
                size: autoType === "stock_ai" ? "lg" : "md",
                position: loaded.length,
                config: {},
              },
            ];
            void saveDashboardLayout(
              loaded.map((w, i) => ({
                widget_type: w.widget_type,
                size: w.size,
                position: i,
                config: w.config ?? {},
              })),
            );
          }
        }
        setWidgets(orderWidgets(loaded));
      })
      .catch(() => setWidgets([]))
      .finally(() => setLoading(false));
  }, []);

  const persistLayout = useCallback(async (updated: WidgetWithId[]) => {
    setSaving(true);
    try {
      await saveDashboardLayout(
        updated.map((w, i) => ({
          widget_type: w.widget_type,
          size: w.size,
          position: i,
          config: w.config ?? {},
        }))
      );
    } catch {
      // ignore save errors silently
    } finally {
      setSaving(false);
    }
  }, []);

  function handleAddWidget(widget: WidgetItem) {
    const updated: WidgetWithId[] = [
      ...widgets,
      { ...widget, position: widgets.length },
    ];
    setWidgets(updated);
    persistLayout(updated);
  }

  function handleRemoveWidget(idx: number) {
    const updated = widgets.filter((_, i) => i !== idx);
    setWidgets(updated);
    persistLayout(updated);
  }

  function handleResizeWidget(idx: number, newSize: "sm" | "md" | "lg") {
    const updated = widgets.map((w, i) =>
      i === idx ? { ...w, size: newSize } : w
    );
    setWidgets(updated);
    persistLayout(updated);
  }

  const existingTypes = widgets.map((w) => w.widget_type);

  return (
    <div className="page-container dashboard-page">
      <TickerTape />

      <div className="dashboard-toolbar">
        <div>
          <h1 className="page-title">Dashboard</h1>
          {saving && <span className="dashboard-saving">saving…</span>}
        </div>
        <div className="dashboard-toolbar-right">
          <div className="dashboard-search-inline">
            <StockSymbolPicker
              value={searchValue}
              onChange={(opt) => {
                setSearchValue(opt);
                openStock(opt);
              }}
              placeholder="Search any NSE stock…"
            />
          </div>
          <button type="button" onClick={() => setPickerOpen(true)}>
            + Add Widget
          </button>
        </div>
      </div>

      {loading ? (
        <div className="status loading">Loading dashboard…</div>
      ) : widgets.length === 0 ? (
        <div className="dashboard-empty">
          <div className="dashboard-empty-icon">🧩</div>
          <h3>Your dashboard is empty</h3>
          <p>Click <strong>+ Add Widget</strong> to get started</p>
          <button type="button" onClick={() => setPickerOpen(true)}>
            + Add Widget
          </button>
        </div>
      ) : (
        <div className="widget-grid">
          {widgets.map((widget, idx) => (
            <div
              key={`${widget.widget_type}-${idx}`}
              className={`widget-card size-${widget.size}`}
            >
              <div className="widget-header">
                <span className="widget-title">
                  {WIDGET_ICONS[widget.widget_type]}{" "}
                  {WIDGET_LABELS[widget.widget_type] ?? widget.widget_type}
                </span>
                <div className="widget-actions">
                  {/* Resize buttons */}
                  {(["sm", "md", "lg"] as const).map((s) => (
                    <button
                      key={s}
                      type="button"
                      className="widget-action-btn"
                      title={`Resize to ${s}`}
                      style={{
                        color: widget.size === s ? "var(--accent)" : undefined,
                      }}
                      onClick={() => handleResizeWidget(idx, s)}
                    >
                      {s === "sm" ? "S" : s === "md" ? "M" : "L"}
                    </button>
                  ))}
                  <button
                    type="button"
                    className="widget-action-btn"
                    title="Remove widget"
                    onClick={() => handleRemoveWidget(idx)}
                  >
                    ✕
                  </button>
                </div>
              </div>
              <div className="widget-body">
                <WidgetContent widget={widget} />
              </div>
            </div>
          ))}
        </div>
      )}

      {pickerOpen && (
        <WidgetPicker
          onClose={() => setPickerOpen(false)}
          onAdd={handleAddWidget}
          existingTypes={existingTypes}
        />
      )}

      <StockDetailModal stock={selectedStock} onClose={() => setSelectedStock(null)} />
    </div>
  );
}
