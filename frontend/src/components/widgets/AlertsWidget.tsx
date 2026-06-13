import { useCallback, useEffect, useMemo, useState } from "react";
import { deletePriceAlert, fetchPriceAlerts } from "../../api";
import type { PriceAlert } from "../../types/alerts";
import { formatIST } from "../../lib/formatTime";
import { displaySymbol } from "../../utils/tradingView";
import {
  freshQuote,
  livePct,
  useLiveTicks,
  useWatchSymbols,
} from "../../context/LiveTicksContext";

interface Props {
  size: "sm" | "md" | "lg";
}

const SEVEN_DAYS_MS = 7 * 24 * 60 * 60 * 1000;

function fmtPrice(value: number | null | undefined): string {
  if (value == null) return "—";
  return `₹${value.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}

function PctCell({ value }: { value: number | null | undefined }) {
  if (value == null) return <>—</>;
  const cls = value >= 0 ? "pct-pos" : "pct-neg";
  const sign = value >= 0 ? "+" : "";
  return (
    <span className={cls}>
      {sign}
      {value.toFixed(2)}%
    </span>
  );
}

function isRecentTriggered(alert: PriceAlert): boolean {
  if (alert.active || !alert.triggered_at) return false;
  const t = new Date(alert.triggered_at).getTime();
  if (Number.isNaN(t)) return false;
  return Date.now() - t <= SEVEN_DAYS_MS;
}

export default function AlertsWidget({ size: _size }: Props) {
  const [alerts, setAlerts] = useState<PriceAlert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"all" | "active" | "triggered">("active");

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    setError(null);
    try {
      const data = await fetchPriceAlerts(false, true);
      setAlerts(data.alerts);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load alerts");
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const id = window.setInterval(() => void load(true), 30_000);
    return () => window.clearInterval(id);
  }, [load]);

  // Stream the alert symbols; overlay LTP + today's % from live ticks (~3s).
  const alertSymbols = useMemo(
    () => Array.from(new Set(alerts.filter((a) => a.active).map((a) => a.symbol))),
    [alerts],
  );
  useWatchSymbols(alertSymbols);
  const { quotes } = useLiveTicks();

  const liveAlerts = useMemo(() => {
    return alerts.map((a) => {
      const q = freshQuote(quotes, a.symbol);
      if (!q || q.price === a.ltp) return a;
      return {
        ...a,
        ltp: q.price,
        change_day_pct: livePct(q.price, a.ltp, a.change_day_pct) ?? a.change_day_pct,
      };
    });
  }, [alerts, quotes]);

  const activeAlerts = useMemo(() => liveAlerts.filter((a) => a.active), [liveAlerts]);
  const triggeredAlerts = useMemo(
    () => liveAlerts.filter(isRecentTriggered),
    [liveAlerts],
  );

  const visible = useMemo(() => {
    if (tab === "active") return activeAlerts;
    if (tab === "triggered") return triggeredAlerts;
    return [...activeAlerts, ...triggeredAlerts].sort((a, b) => {
      if (a.active !== b.active) return a.active ? -1 : 1;
      const ta = a.active ? a.created_at : a.triggered_at ?? a.created_at;
      const tb = b.active ? b.created_at : b.triggered_at ?? b.created_at;
      return tb.localeCompare(ta);
    });
  }, [tab, activeAlerts, triggeredAlerts]);

  const handleDelete = async (id: number) => {
    try {
      await deletePriceAlert(id);
      setAlerts((prev) => prev.filter((a) => a.id !== id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  };

  if (loading && alerts.length === 0) {
    return <div className="widget-loading">Loading alerts…</div>;
  }

  return (
    <div className="alerts-widget">
      <div className="alerts-widget-tabs">
        <button
          type="button"
          className={`alerts-widget-tab${tab === "all" ? " active" : ""}`}
          onClick={() => setTab("all")}
        >
          All ({activeAlerts.length + triggeredAlerts.length})
        </button>
        <button
          type="button"
          className={`alerts-widget-tab${tab === "active" ? " active" : ""}`}
          onClick={() => setTab("active")}
        >
          Active ({activeAlerts.length})
        </button>
        <button
          type="button"
          className={`alerts-widget-tab${tab === "triggered" ? " active" : ""}`}
          onClick={() => setTab("triggered")}
        >
          Triggered ({triggeredAlerts.length})
        </button>
      </div>

      {error && <p className="status error">{error}</p>}

      {visible.length === 0 ? (
        <p className="alerts-widget-empty">
          {tab === "triggered"
            ? "No triggered alerts in the last 7 days."
            : tab === "active"
              ? "No active alerts. Use + Alert on any stock."
              : "No alerts yet."}
        </p>
      ) : (
        <div className="alerts-widget-table-wrap">
          <table className="alerts-widget-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Status</th>
                <th>LTP</th>
                <th>Day %</th>
                <th>7D %</th>
                <th>Condition</th>
                <th>When</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {visible.map((alert) => (
                <tr key={alert.id} className={alert.active ? "" : "alerts-widget-row-dead"}>
                  <td>
                    <strong>{displaySymbol(alert.symbol)}</strong>
                  </td>
                  <td>
                    <span
                      className={`alerts-widget-status${alert.active ? " alerts-widget-status-active" : ""}`}
                    >
                      {alert.active ? "Active" : "Triggered"}
                    </span>
                  </td>
                  <td>{fmtPrice(alert.ltp)}</td>
                  <td>
                    <PctCell value={alert.change_day_pct} />
                  </td>
                  <td>
                    <PctCell value={alert.change_7d_pct} />
                  </td>
                  <td>
                    {alert.direction === "above" ? "Above" : "Below"}{" "}
                    {fmtPrice(alert.target_price)}
                  </td>
                  <td className="alerts-widget-when">
                    {alert.active ? (
                      formatIST(alert.created_at)
                    ) : (
                      formatIST(alert.triggered_at)
                    )}
                  </td>
                  <td>
                    <button
                      type="button"
                      className="alerts-delete-btn"
                      onClick={() => void handleDelete(alert.id)}
                    >
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="meta alerts-widget-footnote">
        Triggered alerts older than 7 days are hidden. Manage all alerts on the Alerts page.
      </p>
    </div>
  );
}
