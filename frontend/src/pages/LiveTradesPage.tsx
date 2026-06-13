import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import SymbolLink from "../components/SymbolLink";
import LightweightStockChart from "../components/LightweightStockChart";
import CandidateScreenerSettings from "../components/CandidateScreenerSettings";
import VolumeBadge from "../components/VolumeBadge";
import SortableTh from "../components/SortableTh";
import { useTableSort } from "../hooks/useTableSort";
import { useLiveTradeSSE } from "../context/LiveTradeSSEContext";
import {
  fetchBrStScanResults,
  fetchMultiYearScanResults,
  fetchStrategyTrades,
  forceResetLiveTrading,
  removeLiveTradeCandidate,
} from "../api";
import type { BrStMatch } from "../types/brst";
import type {
  LiveTrade,
  LiveTradeCandidate,
  LiveTradingMode,
  LiveTradingState,
  StrategyTradeResult,
} from "../types/liveTrading";
import type { MultiYearMatch } from "../types/multiYear";
import { NSE_SESSION_LABEL, useNseSessionPhase } from "../lib/nseSession";
import { formatIST } from "../lib/formatTime";
import { getChartColors } from "../lib/chartTheme";
import TimestampLabel from "../components/TimestampLabel";

function fmt(value: number | null | undefined, prefix = ""): string {
  if (value == null) return "-";
  return `${prefix}${value.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}

function tradeQty(t: LiveTrade): number {
  return Math.trunc(t.qty);
}

function tradeInvested(t: LiveTrade): number {
  return Math.round(tradeQty(t) * t.entry_price * 100) / 100;
}

function fmtQty(qty: number): string {
  return Math.trunc(qty).toLocaleString("en-IN", { maximumFractionDigits: 0 });
}

function pnlClass(v: number | null | undefined): string {
  if (v == null) return "";
  return v > 0 ? "positive" : v < 0 ? "negative" : "";
}

function fmtPointDiff(entry: number, level: number | null | undefined): string {
  if (level == null || entry <= 0) return "-";
  const pts = level - entry;
  const pct = (pts / entry) * 100;
  const sign = pts >= 0 ? "+" : "";
  return `${sign}${pts.toFixed(2)} (${sign}${pct.toFixed(2)}%)`;
}

function SymbolWithChart({
  symbol,
  suffix,
  sub,
}: {
  symbol: string;
  suffix?: ReactNode;
  sub?: string | null;
}) {
  return (
    <>
      <span className="lt-sym-inline">
        <SymbolLink symbol={symbol} />
        {suffix}
      </span>
      {sub && <span className="lt-company-sub">{sub}</span>}
    </>
  );
}

const SOURCE_LABEL: Record<string, string> = {
  brst: "Year Breakout",
  multi_year: "Multi-Year",
  golden: "Golden Stocks",
  weekly: "Weekly Stocks",
  darvas: "Darvas Box",
  mean_reversion: "Mean Reversion",
  vol_squeeze: "Volatility Squeeze",
  volume_surge: "Volume Surge",
};

type ScanMatch = BrStMatch | MultiYearMatch;

const MODE_CHIP: Record<LiveTradingMode, { label: string; cls: string; hint: string }> = {
  live: { label: "Engine · Live", cls: "live", hint: "Market open with live data — entries active" },
  analysis: { label: "Engine · Analysis", cls: "analysis", hint: "Off-hours prep: screeners refreshed, levels computed" },
  market_off: { label: "Engine · Idle", cls: "idle", hint: `Outside NSE hours (${NSE_SESSION_LABEL})` },
  off: { label: "Engine · Off", cls: "idle", hint: "Engine disabled" },
};

function CandidateCards({
  rows,
  matchByKey,
  onRemove,
  removingKey,
}: {
  rows: LiveTradeCandidate[];
  matchByKey: Map<string, ScanMatch>;
  onRemove: (c: LiveTradeCandidate) => void;
  removingKey: string | null;
}) {
  if (rows.length === 0) {
    return (
      <p className="lt-empty">
        No candidates yet. Use Sync from Screeners to import stocks from your saved scans.
      </p>
    );
  }

  return (
    <div className="lt-candidate-grid">
      {rows.map((c) => {
        const match = matchByKey.get(`${c.symbol}:${c.source}`);
        const price = c.last_price ?? match?.price;
        const bars = match?.bars ?? [];
        const testPoints = match?.test_points ?? [];
        const key = `${c.symbol}:${c.source}`;
        const canRemove = c.status !== "in_trade";
        const bullets = c.bullets ?? [];

        return (
          <div key={key} className="lt-candidate-card">
            <div className="lt-candidate-card-top">
              <label
                className="lt-candidate-include"
                onClick={(e) => e.stopPropagation()}
                title={canRemove ? "Uncheck to remove from candidates" : "In active trade"}
              >
                <input
                  type="checkbox"
                  checked
                  disabled={!canRemove || removingKey === key}
                  onChange={() => {
                    if (canRemove) onRemove(c);
                  }}
                />
                <span>Include</span>
              </label>
            </div>

            <div className="lt-candidate-card-header">
              <div>
                <h3>
                  <SymbolLink symbol={c.symbol} />
                </h3>
                <span className="lt-candidate-sub">{c.company_name ?? c.symbol}</span>
              </div>
              <div className="lt-candidate-price">
                <div>{price != null ? `₹${price}` : "-"}</div>
                {match && "distance_pct" in match && match.distance_pct != null && (
                  <span>{match.distance_pct}% from high</span>
                )}
              </div>
            </div>

            <div className="lt-candidate-badges">
              <span className="lt-badge-source">{SOURCE_LABEL[c.source] ?? c.source}</span>
              <span className={`lt-status lt-status-${c.status}`}>{c.status}</span>
              {match && "tests_count" in match && match.tests_count != null && (
                <span className="lt-badge-tests">✓ Tested {match.tests_count}×</span>
              )}
              <span className="lt-badge-resistance">Resistance: ₹{c.resistance}</span>
              {match && <VolumeBadge match={match} />}
            </div>

            <div className="lt-candidate-metrics">
              <div className="lt-candidate-metric">
                <span className="lt-candidate-metric-label">Entry point</span>
                <span
                  className="lt-candidate-metric-value"
                  title={c.entry_point ?? undefined}
                >
                  {c.resistance != null ? `₹${c.resistance}` : "—"}
                </span>
              </div>
              <div className="lt-candidate-metric">
                <span className="lt-candidate-metric-label">Target</span>
                <span className="lt-candidate-metric-value positive">
                  {c.target_price != null ? `₹${c.target_price}` : "—"}
                </span>
              </div>
              <div className="lt-candidate-metric">
                <span className="lt-candidate-metric-label">Stop loss</span>
                <span className="lt-candidate-metric-value negative">
                  {c.stop_price != null ? `₹${c.stop_price}` : "—"}
                </span>
              </div>
            </div>

            {bullets.filter((b) => !/^Smart Swing:/i.test(b)).length > 0 && (
              <div className="lt-candidate-why-block">
                <h4 className="lt-candidate-entry-title">Why selected</h4>
                <ul className="lt-candidate-bullets">
                  {bullets
                    .filter((b) => !/^Smart Swing:/i.test(b))
                    .map((b) => (
                      <li key={b}>{b}</li>
                    ))}
                </ul>
              </div>
            )}

            {bars.length > 0 ? (
              <div className="lt-candidate-chart">
                <LightweightStockChart
                  bars={bars}
                  symbol={c.symbol}
                  height={200}
                  markers={testPoints.map((tp) => ({
                    time: tp.time,
                    position: "aboveBar" as const,
                    color: "#f59e0b",
                    shape: "arrowDown" as const,
                    text: `Test: ₹${tp.price}`,
                  }))}
                  priceLines={[{ price: c.resistance, color: getChartColors().down, title: "Resistance" }]}
                />
              </div>
            ) : null}

            {c.rationale && (
              <p className="lt-candidate-why">{c.rationale}</p>
            )}

            <div className="lt-candidate-footer">
              {c.added_at && (
                <span className="lt-candidate-added-at">
                  Candidate since {formatIST(c.added_at)}
                </span>
              )}
              {c.updated_at && (
                <span className="lt-candidate-added-at">
                  Price updated {formatIST(c.updated_at)}
                </span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function tradeUnrealized(t: LiveTrade): { abs: number; pct: number } {
  const live = t.last_price ?? t.entry_price;
  const qty = tradeQty(t);
  const abs = Math.round(qty * (live - t.entry_price) * 100) / 100;
  const pct = ((live - t.entry_price) / t.entry_price) * 100;
  return { abs, pct };
}

function tradeSortValue(t: LiveTrade, key: string): string | number | null {
  const { abs, pct } = tradeUnrealized(t);

  switch (key) {
    case "symbol":
      return t.symbol;
    case "source":
      return SOURCE_LABEL[t.source] ?? t.source;
    case "entry_price":
      return t.entry_price;
    case "entry_time":
      return t.entry_time;
    case "qty":
      return tradeQty(t);
    case "notional":
      return tradeInvested(t);
    case "ltp":
      return t.last_price;
    case "target_pts":
      return t.target_price != null ? t.target_price - t.entry_price : null;
    case "stop_pts":
      return t.stop_price != null ? t.stop_price - t.entry_price : null;
    case "peak":
      return t.peak_price;
    case "pnl_abs":
      return abs;
    case "pnl_pct":
      return pct;
    default:
      return null;
  }
}

function ReportIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6z"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinejoin="round"
      />
      <path d="M14 2v6h6M8 13h8M8 17h8M8 9h2" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" />
    </svg>
  );
}

function LiveTradesActionsMenu({
  entriesPaused,
  entriesPauseLoading,
  reportLoading,
  resetLoading,
  marketOpen,
  analysisOverride,
  modeLoading,
  onSetAnalysis,
  onToggleEntriesPause,
  onReport,
  onForceReset,
}: {
  entriesPaused: boolean;
  entriesPauseLoading: boolean;
  reportLoading: boolean;
  resetLoading: boolean;
  marketOpen: boolean;
  analysisOverride: boolean;
  modeLoading: boolean;
  onSetAnalysis: (enabled: boolean) => void;
  onToggleEntriesPause: () => void;
  onReport: () => void;
  onForceReset: () => void;
}) {
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const busy = entriesPauseLoading || reportLoading || resetLoading;

  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open]);

  const run = (action: () => void) => {
    setOpen(false);
    action();
  };

  return (
    <div className="lt-actions-menu" ref={menuRef}>
      <button
        type="button"
        className="lt-actions-menu-btn toolbar-btn"
        aria-label="Live trades actions"
        aria-expanded={open}
        aria-haspopup="menu"
        disabled={busy}
        onClick={() => setOpen((v) => !v)}
        title="Live trades actions"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
          <circle cx="12" cy="5" r="1.75" />
          <circle cx="12" cy="12" r="1.75" />
          <circle cx="12" cy="19" r="1.75" />
        </svg>
      </button>
      {open && (
        <div className="lt-actions-menu-dropdown" role="menu">
          {!marketOpen && (
            <button
              type="button"
              role="menuitem"
              className="lt-actions-menu-item"
              disabled={modeLoading}
              title="Off-hours prep: refresh screeners and compute levels"
              onClick={() => run(() => onSetAnalysis(!analysisOverride))}
            >
              {modeLoading
                ? "Switching mode…"
                : analysisOverride
                  ? "Stop analysis mode"
                  : "Run analysis mode"}
            </button>
          )}
          <button
            type="button"
            role="menuitem"
            className={`lt-actions-menu-item${entriesPaused ? " active" : ""}`}
            disabled={entriesPauseLoading}
            onClick={() => run(onToggleEntriesPause)}
          >
            {entriesPauseLoading
              ? "Updating entries…"
              : entriesPaused
                ? "Resume entries"
                : "Pause entries"}
          </button>
          <button
            type="button"
            role="menuitem"
            className="lt-actions-menu-item"
            disabled={reportLoading}
            onClick={() => run(onReport)}
          >
            {reportLoading ? "Sending report…" : "Report to clients"}
          </button>
          <button
            type="button"
            role="menuitem"
            className="lt-actions-menu-item danger"
            disabled={resetLoading}
            onClick={() => run(onForceReset)}
          >
            {resetLoading ? "Resetting…" : "Force reset"}
          </button>
        </div>
      )}
    </div>
  );
}

function EntryConditionsPanel() {
  const [open, setOpen] = useState(false);

  return (
    <div className="lt-entry-info scan-rules-panel">
      <button
        type="button"
        className="scan-rules-toggle"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        {open ? "▾" : "▸"} Entry Conditions
      </button>
      {open && (
        <div className="scan-rules-body">
          <ul className="scan-rules-list">
            <li>
              <strong>Price Breakout:</strong> Stock price breaks above resistance (from screener scan)
            </li>
            <li>
              <strong>Volume Confirmation:</strong> Recent volume exceeds 50-day average threshold
              (1.5x minimum) for breakout screeners
            </li>
            <li>
              <strong>Portfolio:</strong> ₹10,00,000 starting capital. Realized P&amp;L from closed
              trades adds to (or reduces) available cash. Max ₹1,00,000 per stock; no new entries when
              cash is exhausted (max ~10 open positions).
            </li>
            <li>
              <strong>Strategy:</strong> Smart Swing 5/3 — Target +5%, Stop −3%, Trailing stop after +3%
              gain (2% trail gap), Time stop 15 days if gain &lt; 1.5%
            </li>
          </ul>
        </div>
      )}
    </div>
  );
}

function ClosedTradesModal({
  rows,
  onClose,
}: {
  rows: LiveTrade[];
  onClose: () => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [onClose]);

  const totalPnl = useMemo(
    () => rows.reduce((sum, t) => sum + (t.pnl_abs ?? 0), 0),
    [rows],
  );

  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="modal-panel lt-closed-trades-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="lt-closed-trades-title"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="modal-header">
          <div className="modal-title-wrap">
            <h2 id="lt-closed-trades-title">Closed trades report</h2>
            <span className="lt-closed-modal-sub">
              {rows.length} trade{rows.length !== 1 ? "s" : ""}
              {rows.length > 0 && (
                <>
                  {" · "}
                  <span className={pnlClass(totalPnl)}>
                    {totalPnl >= 0 ? "+" : ""}
                    {fmt(totalPnl, "₹")} till date
                  </span>
                </>
              )}
            </span>
          </div>
          <button type="button" className="modal-close" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </header>
        <div className="modal-body">
          {rows.length === 0 ? (
            <p className="lt-empty">No closed trades yet.</p>
          ) : (
            <div className="lt-table-wrap">
              <table className="lt-table lt-closed-detail-table">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Scanner</th>
                    <th>Qty</th>
                    <th>Investment</th>
                    <th>Candidate since</th>
                    <th>Buy date</th>
                    <th>Entry ₹</th>
                    <th>Sell date</th>
                    <th>Exit ₹</th>
                    <th>Reason</th>
                    <th>Days</th>
                    <th>Peak ₹</th>
                    <th>Trough ₹</th>
                    <th>P&amp;L</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((t) => {
                    const pnl = t.pnl_abs ?? 0;
                    const pct = t.pnl_pct ?? 0;
                    return (
                      <tr key={t.id}>
                        <td className="lt-sym">
                          <SymbolWithChart symbol={t.symbol} sub={t.company_name} />
                        </td>
                        <td>{SOURCE_LABEL[t.source] ?? t.source}</td>
                        <td>{fmtQty(t.qty)}</td>
                        <td>{fmt(tradeInvested(t), "₹")}</td>
                        <td className="lt-date-cell">{formatIST(t.candidate_added_at)}</td>
                        <td className="lt-date-cell">{formatIST(t.entry_time)}</td>
                        <td>{fmt(t.entry_price, "₹")}</td>
                        <td className="lt-date-cell">{formatIST(t.exit_time)}</td>
                        <td>{fmt(t.exit_price, "₹")}</td>
                        <td>{t.exit_reason ?? "-"}</td>
                        <td>{t.days_held ?? "-"}</td>
                        <td>{fmt(t.peak_price, "₹")}</td>
                        <td>{fmt(t.trough_price, "₹")}</td>
                        <td className={`lt-pnl-cell ${pnlClass(pnl)}`}>
                          <span className={`lt-pnl-abs ${pnlClass(pnl)}`}>
                            {pnl >= 0 ? "+" : ""}
                            {fmt(pnl, "₹")}
                          </span>
                          <span className={`lt-pnl-row-pct ${pnlClass(pnl)}`}>
                            {pct >= 0 ? "+" : ""}
                            {pct.toFixed(2)}%
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function StrategyTradesModal({
  strategyKey,
  strategyLabel,
  onClose,
}: {
  strategyKey: string;
  strategyLabel: string;
  onClose: () => void;
}) {
  const [trades, setTrades] = useState<StrategyTradeResult[]>([]);
  const [loadingTrades, setLoadingTrades] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [onClose]);

  useEffect(() => {
    setLoadingTrades(true);
    setLoadError(null);
    fetchStrategyTrades(strategyKey)
      .then((data) => setTrades(data.trades))
      .catch((err) => setLoadError(err instanceof Error ? err.message : "Failed to load"))
      .finally(() => setLoadingTrades(false));
  }, [strategyKey]);

  const totalPnl = useMemo(
    () => trades.reduce((sum, t) => sum + t.pnl_abs, 0),
    [trades],
  );

  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="modal-panel lt-closed-trades-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="lt-strat-trades-title"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="modal-header">
          <div className="modal-title-wrap">
            <h2 id="lt-strat-trades-title">{strategyLabel} — paper trades</h2>
            {trades.length > 0 && (
              <span className="lt-closed-modal-sub">
                {trades.length} trade{trades.length !== 1 ? "s" : ""}
                {" · "}
                <span className={pnlClass(totalPnl)}>
                  {totalPnl >= 0 ? "+" : ""}
                  {fmt(totalPnl, "₹")} total
                </span>
              </span>
            )}
          </div>
          <button type="button" className="modal-close" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </header>
        <div className="modal-body">
          {loadingTrades && <p className="lt-empty">Loading…</p>}
          {loadError && <p className="lt-empty" style={{ color: "var(--c-red)" }}>{loadError}</p>}
          {!loadingTrades && !loadError && trades.length === 0 && (
            <p className="lt-empty">No trades yet for this strategy.</p>
          )}
          {!loadingTrades && !loadError && trades.length > 0 && (
            <div className="lt-table-wrap">
              <table className="lt-table lt-closed-detail-table">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Qty</th>
                    <th>Entry ₹</th>
                    <th>Entry date</th>
                    <th>Exit ₹</th>
                    <th>Exit date</th>
                    <th>Reason</th>
                    <th>Days</th>
                    <th>Peak ₹</th>
                    <th>Trough ₹</th>
                    <th>P&amp;L</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {trades.map((t, i) => (
                    <tr key={`${t.symbol}-${i}`} className={t.is_open ? "lt-row-open-sim" : undefined}>
                      <td className="lt-sym">
                        <SymbolWithChart symbol={t.symbol} sub={t.company_name} />
                      </td>
                      <td>{fmtQty(t.qty)}</td>
                      <td>{fmt(t.entry_price, "₹")}</td>
                      <td className="lt-date-cell">{formatIST(t.entry_time)}</td>
                      <td>{fmt(t.exit_price, "₹")}</td>
                      <td className="lt-date-cell">
                        {t.is_open ? "—" : formatIST(t.exit_time)}
                      </td>
                      <td>{t.exit_reason}</td>
                      <td>{t.days_held}</td>
                      <td>{fmt(t.peak_price, "₹")}</td>
                      <td>{fmt(t.trough_price, "₹")}</td>
                      <td className={`lt-pnl-cell ${pnlClass(t.pnl_abs)}`}>
                        <span className={`lt-pnl-abs ${pnlClass(t.pnl_abs)}`}>
                          {t.pnl_abs >= 0 ? "+" : ""}
                          {fmt(t.pnl_abs, "₹")}
                        </span>
                        <span className={`lt-pnl-row-pct ${pnlClass(t.pnl_pct)}`}>
                          {t.pnl_pct >= 0 ? "+" : ""}
                          {t.pnl_pct.toFixed(2)}%
                        </span>
                      </td>
                      <td>
                        {t.is_open ? (
                          <span className="lt-badge" style={{ background: "var(--c-blue)" }}>open</span>
                        ) : (
                          <span className="lt-badge">closed</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function StrategyComparisonSection({
  summary,
  previewStrategy,
  lastTickAt,
  stateUpdatedAt,
  onPreviewStrategy,
}: {
  summary: import("../types/liveTrading").StrategySummary | null;
  previewStrategy: string;
  lastTickAt: string | null;
  stateUpdatedAt: string | null;
  onPreviewStrategy: (strategyKey: string) => Promise<void>;
}) {
  const [drilldownKey, setDrilldownKey] = useState<{ key: string; label: string } | null>(null);
  const [previewLoading, setPreviewLoading] = useState<string | null>(null);

  const handleRowClick = useCallback(
    async (key: string) => {
      if (key === previewStrategy) return;
      setPreviewLoading(key);
      try {
        await onPreviewStrategy(key);
      } finally {
        setPreviewLoading(null);
      }
    },
    [onPreviewStrategy, previewStrategy],
  );

  return (
    <section className="lt-section">
      <div className="lt-section-header">
        <div>
          <h2>Strategy comparison</h2>
          <p className="lt-section-sub">
            All {summary?.strategies.length ?? 8} strategies enter and exit in parallel on each signal,
            each with an independent ₹10L paper wallet. Click a row to preview that strategy on the
            dashboard above. Use <strong>Details</strong> for per-trade breakdown.
          </p>
          <div className="lt-section-timestamps">
            <TimestampLabel at={lastTickAt} label="Last tick" />
            <TimestampLabel at={stateUpdatedAt} label="Summary as of" />
          </div>
        </div>
      </div>

      {summary && summary.strategies.length > 0 ? (
        <div className="lt-table-wrap">
          <table className="lt-table lt-summary-table lt-summary-clickable">
            <thead>
              <tr>
                <th>Strategy</th>
                <th>Trades</th>
                <th>Win rate</th>
                <th>Avg / trade</th>
                <th>Total P&L</th>
                <th>Total %</th>
                <th aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {summary.strategies.map((s) => {
                const isPreview = s.key === previewStrategy || s.is_preview;
                return (
                  <tr
                    key={s.key}
                    className={isPreview ? "lt-executed" : ""}
                    onClick={() => void handleRowClick(s.key)}
                    style={{ cursor: previewLoading === s.key ? "wait" : "pointer" }}
                    title="Click to preview this strategy on the dashboard"
                  >
                    <td>
                      {s.label}
                      {isPreview && (
                        <span className="lt-badge">Preview on dashboard</span>
                      )}
                      {previewLoading === s.key && (
                        <span className="lt-badge">Switching…</span>
                      )}
                    </td>
                    <td>{s.trades}</td>
                    <td>{s.win_rate}%</td>
                    <td className={pnlClass(s.avg_pct)}>
                      {s.avg_pct >= 0 ? "+" : ""}
                      {s.avg_pct}%
                    </td>
                    <td className={pnlClass(s.total_pnl_abs)}>{fmt(s.total_pnl_abs, "Rs.")}</td>
                    <td className={pnlClass(s.total_pct)}>
                      {s.total_pct >= 0 ? "+" : ""}
                      {s.total_pct}%
                    </td>
                    <td>
                      <button
                        type="button"
                        className="toolbar-btn lt-strategy-details-btn"
                        onClick={(e) => {
                          e.stopPropagation();
                          setDrilldownKey({ key: s.key, label: s.label });
                        }}
                      >
                        Details
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="lt-empty">No trades yet — the comparison fills in once trades are taken.</p>
      )}

      {drilldownKey && (
        <StrategyTradesModal
          strategyKey={drilldownKey.key}
          strategyLabel={drilldownKey.label}
          onClose={() => setDrilldownKey(null)}
        />
      )}
    </section>
  );
}

function PortfolioStats({
  state,
  openRows,
  closedRows,
}: {
  state: LiveTradingState | null;
  openRows: LiveTrade[];
  closedRows: LiveTrade[];
}) {
  const p = useMemo(() => {
    const starting = state?.starting_capital ?? 1_000_000;
    const realized =
      state?.realized_pnl ?? closedRows.reduce((sum, t) => sum + (t.pnl_abs ?? 0), 0);
    const unrealized =
      state?.unrealized_pnl ?? openRows.reduce((sum, t) => sum + tradeUnrealized(t).abs, 0);
    const totalPnl = state?.total_pnl ?? realized + unrealized;
    const equity = state?.portfolio_equity ?? starting + totalPnl;
    const totalPnlPct =
      state?.total_pnl_pct ?? (starting > 0 ? (totalPnl / starting) * 100 : 0);
    return { starting, realized, unrealized, totalPnl, totalPnlPct, equity };
  }, [state, openRows, closedRows]);

  const todayPnl = state?.today_pnl ?? 0;
  const todayPnlPct = state?.today_pnl_pct ?? 0;
  const cash = state?.available_cash ?? p.starting;
  const deployed = state?.deployed ?? 0;
  const positions = state?.open_positions ?? openRows.length;
  const maxPositions = state?.max_positions ?? 10;
  const maxPerTrade = state?.max_per_trade ?? state?.capital_per_trade ?? 100_000;

  return (
    <div className="lt-stats-grid">
      <div className={`lt-stat-card lt-stat-accent ${pnlClass(p.totalPnl)}`}>
        <span className="lt-stat-label">Total P&amp;L</span>
        <span className={`lt-stat-value ${pnlClass(p.totalPnl)}`}>
          {p.totalPnl >= 0 ? "+" : ""}
          {fmt(p.totalPnl, "₹")}
          <span className="lt-stat-pct">
            {" "}
            ({p.totalPnlPct >= 0 ? "+" : ""}
            {p.totalPnlPct.toFixed(2)}%)
          </span>
        </span>
        <span className={`lt-stat-sub ${pnlClass(todayPnl)}`}>
          Today {todayPnl >= 0 ? "+" : ""}
          {fmt(todayPnl, "₹")} ({todayPnlPct >= 0 ? "+" : ""}
          {todayPnlPct.toFixed(2)}%)
        </span>
      </div>

      <div className="lt-stat-card">
        <span className="lt-stat-label">Equity</span>
        <span className="lt-stat-value">{fmt(p.equity, "₹")}</span>
        <span className="lt-stat-sub">
          realized {p.realized >= 0 ? "+" : ""}
          {fmt(p.realized, "₹")} · open {p.unrealized >= 0 ? "+" : ""}
          {fmt(p.unrealized, "₹")}
        </span>
      </div>

      <div className="lt-stat-card">
        <span className="lt-stat-label">Cash available</span>
        <span className="lt-stat-value">{fmt(cash, "₹")}</span>
        <span className="lt-stat-sub">
          deployed {fmt(deployed, "₹")} · of {fmt(p.starting, "₹")}
        </span>
      </div>

      <div className="lt-stat-card">
        <span className="lt-stat-label">Positions</span>
        <span className="lt-stat-value">
          {positions}
          <span className="lt-stat-pct"> / {maxPositions}</span>
        </span>
        <span className="lt-stat-sub">max {fmt(maxPerTrade, "₹")} per stock</span>
      </div>
    </div>
  );
}

function OpenPositionsSection({
  openRows,
  closedRows,
  onExitTrade,
  exitingTradeId,
}: {
  openRows: LiveTrade[];
  closedRows: LiveTrade[];
  onExitTrade: (tradeId: number) => Promise<void>;
  exitingTradeId: number | null;
}) {
  const [showClosedReport, setShowClosedReport] = useState(false);
  const realized = useMemo(
    () => closedRows.reduce((sum, t) => sum + (t.pnl_abs ?? 0), 0),
    [closedRows],
  );

  return (
    <section className="lt-section lt-open-section">
      <div className="lt-section-header">
        <div>
          <h2>Open positions ({openRows.length})</h2>
          <p className="lt-section-sub">
            Closed trades live in the report — they leave this table the moment they exit.
          </p>
        </div>
        <button
          type="button"
          className="lt-closed-report-btn toolbar-btn"
          title="Closed trades report"
          onClick={() => setShowClosedReport(true)}
        >
          <ReportIcon />
          <span>
            Report · {closedRows.length} closed
            {closedRows.length > 0 && (
              <span className={`lt-report-pnl ${pnlClass(realized)}`}>
                {" "}
                {realized >= 0 ? "+" : ""}
                {fmt(realized, "₹")}
              </span>
            )}
          </span>
        </button>
      </div>

      <TradesTable rows={openRows} onExitTrade={onExitTrade} exitingTradeId={exitingTradeId} />

      {showClosedReport && (
        <ClosedTradesModal rows={closedRows} onClose={() => setShowClosedReport(false)} />
      )}
    </section>
  );
}

function TradesTable({
  rows,
  onExitTrade,
  exitingTradeId,
}: {
  rows: LiveTrade[];
  onExitTrade?: (tradeId: number) => Promise<void>;
  exitingTradeId?: number | null;
}) {
  const getValue = useCallback(
    (row: LiveTrade, key: string) => tradeSortValue(row, key),
    [],
  );
  const { sortedRows, sortKey, sortDir, toggleSort } = useTableSort(
    rows,
    "pnl_abs",
    "desc",
    getValue,
  );

  if (rows.length === 0) {
    return (
      <p className="lt-empty">
        No open positions. Armed candidates enter automatically when price breaks resistance
        during market hours.
      </p>
    );
  }

  return (
    <div className="lt-table-wrap">
      <table className="lt-table">
        <thead>
          <tr>
            <SortableTh label="Symbol" sortKey="symbol" activeKey={sortKey} direction={sortDir} onSort={toggleSort} />
            <SortableTh label="Source" sortKey="source" activeKey={sortKey} direction={sortDir} onSort={toggleSort} />
            <SortableTh label="Entry" sortKey="entry_price" activeKey={sortKey} direction={sortDir} onSort={toggleSort} />
            <SortableTh label="Qty" sortKey="qty" activeKey={sortKey} direction={sortDir} onSort={toggleSort} />
            <SortableTh label="Invested" sortKey="notional" activeKey={sortKey} direction={sortDir} onSort={toggleSort} />
            <SortableTh label="LTP" sortKey="ltp" activeKey={sortKey} direction={sortDir} onSort={toggleSort} />
            <SortableTh label="Target" sortKey="target_pts" activeKey={sortKey} direction={sortDir} onSort={toggleSort} />
            <SortableTh label="Stop" sortKey="stop_pts" activeKey={sortKey} direction={sortDir} onSort={toggleSort} />
            <SortableTh label="Peak" sortKey="peak" activeKey={sortKey} direction={sortDir} onSort={toggleSort} />
            <SortableTh label="P&L" sortKey="pnl_abs" activeKey={sortKey} direction={sortDir} onSort={toggleSort} />
            {onExitTrade && <th aria-label="Actions" />}
          </tr>
        </thead>
        <tbody>
          {sortedRows.map((t) => {
            const { abs, pct } = tradeUnrealized(t);
            return (
              <tr key={t.id} title={t.rationale ?? ""}>
                <td className="lt-sym">
                  <SymbolWithChart symbol={t.symbol} sub={t.company_name} />
                </td>
                <td>{SOURCE_LABEL[t.source] ?? t.source}</td>
                <td>
                  {fmt(t.entry_price, "₹")}
                  <span className="lt-cell-sub">{formatIST(t.entry_time)}</span>
                </td>
                <td>{fmtQty(t.qty)}</td>
                <td>{fmt(tradeInvested(t), "₹")}</td>
                <td>
                  {fmt(t.last_price, "₹")}
                  <span className="lt-cell-sub">{formatIST(t.updated_at)}</span>
                </td>
                <td className="positive">{fmtPointDiff(t.entry_price, t.target_price)}</td>
                <td className="negative">{fmtPointDiff(t.entry_price, t.stop_price)}</td>
                <td>{fmt(t.peak_price, "₹")}</td>
                <td className={`lt-pnl-cell ${pnlClass(abs)}`}>
                  <span className={`lt-pnl-abs ${pnlClass(abs)}`}>
                    {abs >= 0 ? "+" : ""}
                    {fmt(abs, "₹")}
                  </span>
                  <span className={`lt-pnl-row-pct ${pnlClass(abs)}`}>
                    {pct >= 0 ? "+" : ""}
                    {pct.toFixed(2)}%
                  </span>
                </td>
                {onExitTrade && (
                  <td className="lt-actions-cell">
                    <button
                      type="button"
                      className="lt-exit-btn toolbar-btn"
                      disabled={exitingTradeId === t.id}
                      title={`Exit ${t.symbol} at last price`}
                      onClick={() => {
                        if (
                          window.confirm(
                            `Exit ${t.symbol} now at ${fmt(t.last_price ?? t.entry_price, "₹")}?`,
                          )
                        ) {
                          void onExitTrade(t.id);
                        }
                      }}
                    >
                      {exitingTradeId === t.id ? "Exiting…" : "Exit"}
                    </button>
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default function LiveTradesPage() {
  const {
    state,
    candidates,
    trades,
    summary,
    loading,
    error,
    modeLoading,
    entriesPauseLoading,
    reportLoading,
    reportMessage,
    setAnalysisOverride,
    setEntriesPaused,
    setPreviewStrategyKey,
    exitTrade,
    reportToClients,
    refreshFromBackend,
  } = useLiveTradeSSE();

  const [brstMatches, setBrstMatches] = useState<BrStMatch[]>([]);
  const [multiMatches, setMultiMatches] = useState<MultiYearMatch[]>([]);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const [showScreenerSettings, setShowScreenerSettings] = useState(false);
  const [removingKey, setRemovingKey] = useState<string | null>(null);
  const [exitingTradeId, setExitingTradeId] = useState<number | null>(null);
  const [resetLoading, setResetLoading] = useState(false);

  useEffect(() => {
    fetchBrStScanResults().then((d) => setBrstMatches(d.matches as BrStMatch[])).catch(() => {});
    fetchMultiYearScanResults()
      .then((d) => setMultiMatches(d.matches as MultiYearMatch[]))
      .catch(() => {});
  }, []);

  const openTrades = useMemo(() => trades.filter((t) => t.status === "open"), [trades]);
  const closedTrades = useMemo(
    () =>
      trades
        .filter((t) => t.status === "closed")
        .sort((a, b) => {
          const ta = a.exit_time ?? a.updated_at ?? "";
          const tb = b.exit_time ?? b.updated_at ?? "";
          return tb.localeCompare(ta);
        }),
    [trades],
  );
  const matchByKey = useMemo(() => {
    const map = new Map<string, ScanMatch>();
    for (const m of brstMatches) map.set(`${m.symbol}:brst`, m);
    for (const m of multiMatches) map.set(`${m.symbol}:multi_year`, m);
    return map;
  }, [brstMatches, multiMatches]);

  const handleExitTrade = useCallback(
    async (tradeId: number) => {
      setExitingTradeId(tradeId);
      try {
        await exitTrade(tradeId);
        setSyncMessage(null);
      } catch (err) {
        setSyncMessage(err instanceof Error ? err.message : "Failed to exit trade");
      } finally {
        setExitingTradeId(null);
      }
    },
    [exitTrade],
  );

  const handleRemoveCandidate = useCallback(
    async (c: LiveTradeCandidate) => {
      const key = `${c.symbol}:${c.source}`;
      setRemovingKey(key);
      try {
        await removeLiveTradeCandidate(c.symbol, c.source);
        await refreshFromBackend();
      } catch (err) {
        setSyncMessage(err instanceof Error ? err.message : "Failed to remove candidate");
      } finally {
        setRemovingKey(null);
      }
    },
    [refreshFromBackend],
  );

  const handleForceReset = useCallback(async () => {
    const ok = window.confirm(
      "Force reset will delete all trades and candidates and restore every strategy wallet to ₹10L. This cannot be undone. Continue?",
    );
    if (!ok) return;
    setResetLoading(true);
    setSyncMessage(null);
    try {
      const result = await forceResetLiveTrading();
      setSyncMessage(result.message);
      await refreshFromBackend();
    } catch (err) {
      setSyncMessage(err instanceof Error ? err.message : "Force reset failed");
    } finally {
      setResetLoading(false);
    }
  }, [refreshFromBackend]);

  const mode = state?.mode ?? "market_off";
  const marketOpen = state?.market_open ?? false;
  const nseSessionPhase = useNseSessionPhase();
  const nseSessionOpen = nseSessionPhase !== "closed";
  const analysisOverride = state?.analysis_override ?? false;

  return (
    <div className="page live-trades-page">
      <div className="lt-page-head">
        <div>
          <h1 className="page-title">Portfolio</h1>
        </div>
        <div className="lt-page-top-bar">
          <LiveTradesActionsMenu
            entriesPaused={Boolean(state?.entries_paused)}
            entriesPauseLoading={entriesPauseLoading}
            reportLoading={reportLoading}
            resetLoading={resetLoading}
            marketOpen={marketOpen}
            analysisOverride={analysisOverride}
            modeLoading={modeLoading}
            onSetAnalysis={setAnalysisOverride}
            onToggleEntriesPause={() => void setEntriesPaused(!state?.entries_paused)}
            onReport={() => void reportToClients()}
            onForceReset={() => void handleForceReset()}
          />
        </div>
      </div>

      <div className="lt-meta-line">
        <span
          className={`lt-session-chip ${
            nseSessionPhase === "open" ? "live" : nseSessionPhase === "pre_open" ? "preopen" : "closed"
          }`}
        >
          <span className="market-session-dot" aria-hidden />
          NSE {nseSessionPhase === "open" ? "Open" : nseSessionPhase === "pre_open" ? "Pre-Open" : "Closed"}
        </span>
        <span
          className={`lt-session-chip lt-mode-chip-${MODE_CHIP[mode]?.cls ?? "idle"}`}
          title={MODE_CHIP[mode]?.hint}
        >
          {MODE_CHIP[mode]?.label ?? mode}
        </span>
        <span>
          Last tick <strong>{formatIST(state?.last_tick_at ?? null)}</strong>
        </span>
        {state?.last_data_at && (
          <span>
            Data refreshed <strong>{formatIST(state.last_data_at)}</strong>
          </span>
        )}
        {!nseSessionOpen && (
          <span className="lt-meta-hint">
            Showing end-of-day data (3:30 pm IST close) — switch to Market Analysis for off-hours
            prep
          </span>
        )}
        {nseSessionPhase === "pre_open" && (
          <span className="lt-meta-hint">
            Pre-open session — first prices from ~9:07, normal trading (and engine entries) from
            9:15
          </span>
        )}
        {nseSessionPhase === "open" && !marketOpen && mode === "market_off" && (
          <span className="lt-meta-hint">engine syncs within ~30s at session open</span>
        )}
      </div>

      <PortfolioStats state={state} openRows={openTrades} closedRows={closedTrades} />

      {reportMessage && (
        <div className={`status ${reportMessage.includes("failed") ? "error" : "loading"}`}>
          {reportMessage}
        </div>
      )}

      {syncMessage && (
        <div
          className={`status ${
            syncMessage.includes("failed") ||
            syncMessage.includes("error") ||
            syncMessage.includes("Cannot") ||
            syncMessage.includes("No screener")
              ? "error"
              : "loading"
          }`}
        >
          {syncMessage}
        </div>
      )}

      {error && <div className="status error">{error}</div>}

      {state?.entries_paused && (
        <div className="status loading lt-entries-paused-banner">
          New entries are paused. Open positions still update and can hit stop, target, or manual exit.
        </div>
      )}

      <OpenPositionsSection
        openRows={openTrades}
        closedRows={closedTrades}
        onExitTrade={handleExitTrade}
        exitingTradeId={exitingTradeId}
      />

      <EntryConditionsPanel />

      <StrategyComparisonSection
        summary={summary}
        previewStrategy={state?.preview_strategy ?? summary?.preview_strategy ?? "smart_swing"}
        lastTickAt={state?.last_tick_at ?? null}
        stateUpdatedAt={state?.updated_at ?? null}
        onPreviewStrategy={setPreviewStrategyKey}
      />

      <section className="lt-section">
        <div className="lt-section-header">
          <div>
            <h2>Candidates ({candidates.length})</h2>
            <p className="lt-section-sub">
              Uncheck <strong>Include</strong> on a card to remove one stock. Each row is one
              symbol + screener pair (same stock from two screeners counts twice). Use Apply
              &amp; sync in settings to align the watchlist with your current scan selection.
            </p>
            <div className="lt-section-timestamps">
              <TimestampLabel at={state?.last_tick_at ?? null} label="Last tick" />
            </div>
          </div>
          <button
            type="button"
            className="lt-settings-btn toolbar-btn"
            title="Screener sync settings"
            aria-label="Screener sync settings"
            aria-expanded={showScreenerSettings}
            onClick={() => {
              setSyncMessage(null);
              setShowScreenerSettings((v) => !v);
            }}
          >
            <span className="lt-settings-icon" aria-hidden>
              ⚙
            </span>
          </button>
        </div>

        {showScreenerSettings && (
          <CandidateScreenerSettings
            onClose={() => setShowScreenerSettings(false)}
            onSynced={(msg) => {
              setSyncMessage(msg);
              void refreshFromBackend();
            }}
          />
        )}

        <CandidateCards
          rows={candidates}
          matchByKey={matchByKey}
          onRemove={handleRemoveCandidate}
          removingKey={removingKey}
        />
      </section>

      {loading && <div className="status loading">Loading live trading data…</div>}
    </div>
  );
}
