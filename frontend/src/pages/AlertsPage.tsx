import { useCallback, useEffect, useState } from "react";
import { createPriceAlert, deletePriceAlert, fetchPriceAlerts } from "../api";
import StockSymbolPicker, { type StockSymbolOption } from "../components/StockSymbolPicker";
import TimestampLabel from "../components/TimestampLabel";
import type { AlertDirection, PriceAlert } from "../types/alerts";

function fmtPrice(value: number | null | undefined): string {
  if (value == null) return "-";
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

function displaySymbol(symbol: string): string {
  return symbol.replace(/\.(NS|BO)$/i, "");
}

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<PriceAlert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const [selectedStock, setSelectedStock] = useState<StockSymbolOption | null>(null);
  const [targetPrice, setTargetPrice] = useState("");
  const [direction, setDirection] = useState<AlertDirection>("above");
  const [note, setNote] = useState("");

  const loadAlerts = useCallback(async (options?: { silent?: boolean }) => {
    if (!options?.silent) {
      setLoading(true);
    }
    setError(null);
    try {
      const data = await fetchPriceAlerts();
      setAlerts(data.alerts);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load alerts");
    } finally {
      if (!options?.silent) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    void loadAlerts();
  }, [loadAlerts]);

  useEffect(() => {
    const hasActive = alerts.some((a) => a.active);
    if (!hasActive) return;
    const id = window.setInterval(() => {
      void loadAlerts({ silent: true });
    }, 30_000);
    return () => window.clearInterval(id);
  }, [loadAlerts, alerts]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    const price = Number(targetPrice);
    if (!selectedStock || !Number.isFinite(price) || price <= 0) {
      setError("Pick a stock from the suggestions and enter a valid target price.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await createPriceAlert({
        symbol: selectedStock.symbol,
        company_name: selectedStock.company_name,
        target_price: price,
        direction,
        note: note.trim() || undefined,
      });
      setSelectedStock(null);
      setTargetPrice("");
      setNote("");
      await loadAlerts();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create alert");
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await deletePriceAlert(id);
      setAlerts((prev) => prev.filter((a) => a.id !== id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete alert");
    }
  };

  const activeAlerts = alerts.filter((a) => a.active);
  const triggeredAlerts = alerts.filter((a) => !a.active);

  return (
    <div className="page-container alerts-page">
      <div className="page-header">
        <div>
          <h1>Alerts</h1>
          <p className="page-subtitle">
            Set a price target for any NSE stock. When the price crosses your level, you&apos;ll hear
            a beep in the app and optionally receive an email (toggle Email on/off in the top bar).
          </p>
        </div>
      </div>

      <form className="alerts-create-form" onSubmit={handleCreate}>
        <h3>Create price alert</h3>
        <div className="alerts-form-grid">
          <label>
            Stock
            <StockSymbolPicker
              value={selectedStock}
              onChange={setSelectedStock}
              disabled={submitting}
              placeholder="e.g. INOXINDIA or Inox India"
            />
          </label>
          <label>
            Target price (₹)
            <input
              type="number"
              min="0"
              step="0.05"
              placeholder="1578.80"
              value={targetPrice}
              onChange={(e) => setTargetPrice(e.target.value)}
              disabled={submitting}
            />
          </label>
          <label>
            Condition
            <select
              value={direction}
              onChange={(e) => setDirection(e.target.value as AlertDirection)}
              disabled={submitting}
            >
              <option value="above">Price goes above</option>
              <option value="below">Price goes below</option>
            </select>
          </label>
          <label className="alerts-note-field">
            Note (optional)
            <input
              type="text"
              placeholder="Breakout watch"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              disabled={submitting}
            />
          </label>
        </div>
        <button type="submit" className="toolbar-btn btn-primary" disabled={submitting}>
          {submitting ? "Creating…" : "Add Alert"}
        </button>
      </form>

      {error && <div className="status error">{error}</div>}

      {loading ? (
        <p className="status">Loading alerts…</p>
      ) : (
        <>
          <section className="alerts-section">
            <h3>Active alerts ({activeAlerts.length})</h3>
            {activeAlerts.length === 0 ? (
              <p className="status">No active alerts. Create one above.</p>
            ) : (
              <div className="alerts-table-wrap">
                <table className="alerts-table">
                  <thead>
                    <tr>
                      <th>Symbol</th>
                      <th>LTP</th>
                      <th>Day %</th>
                      <th>7D %</th>
                      <th>Condition</th>
                      <th>Note</th>
                      <th>Created</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {activeAlerts.map((alert) => (
                      <tr key={alert.id}>
                        <td>
                          <strong>{displaySymbol(alert.symbol)}</strong>
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
                        <td>{alert.note || "-"}</td>
                        <td>
                          <TimestampLabel at={alert.created_at} label="Created" />
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
          </section>

          {triggeredAlerts.length > 0 && (
            <section className="alerts-section alerts-section-triggered">
              <h3>Triggered ({triggeredAlerts.length})</h3>
              <div className="alerts-table-wrap">
                <table className="alerts-table">
                  <thead>
                    <tr>
                      <th>Symbol</th>
                      <th>Target</th>
                      <th>Triggered at</th>
                      <th>When</th>
                    </tr>
                  </thead>
                  <tbody>
                    {triggeredAlerts.map((alert) => (
                      <tr key={alert.id}>
                        <td>{displaySymbol(alert.symbol)}</td>
                        <td>
                          {alert.direction === "above" ? "Above" : "Below"}{" "}
                          {fmtPrice(alert.target_price)}
                        </td>
                        <td>{fmtPrice(alert.triggered_price)}</td>
                        <td>
                          <TimestampLabel at={alert.triggered_at} label="Triggered" />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}
