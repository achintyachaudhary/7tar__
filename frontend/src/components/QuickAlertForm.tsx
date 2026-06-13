import { useState } from "react";
import { createPriceAlert } from "../api";
import type { AlertDirection } from "../types/alerts";
import { displaySymbol } from "../utils/tradingView";

interface QuickAlertFormProps {
  symbol: string;
  companyName?: string | null;
  onClose: () => void;
}

export default function QuickAlertForm({ symbol, companyName, onClose }: QuickAlertFormProps) {
  const [targetPrice, setTargetPrice] = useState("");
  const [direction, setDirection] = useState<AlertDirection>("above");
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const price = Number(targetPrice);
    if (!Number.isFinite(price) || price <= 0) {
      setError("Enter a valid target price.");
      return;
    }
    setSubmitting(true);
    setError(null);
    setStatus(null);
    try {
      await createPriceAlert({
        symbol,
        company_name: companyName ?? undefined,
        target_price: price,
        direction,
        note: note.trim() || undefined,
      });
      setStatus(`Alert set for ${displaySymbol(symbol)} ${direction} ₹${price}.`);
      setTargetPrice("");
      setNote("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create alert");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form className="quick-alert" onSubmit={handleSubmit}>
      <h4>Add price alert for {displaySymbol(symbol)}</h4>
      <div className="quick-alert-grid">
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
            autoFocus
          />
        </label>
        <label>
          Note (optional)
          <input
            type="text"
            placeholder="Breakout watch"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            disabled={submitting}
          />
        </label>
        <button type="submit" className="btn-primary" disabled={submitting}>
          {submitting ? "Saving…" : "Set alert"}
        </button>
        <button type="button" className="toolbar-btn" onClick={onClose} disabled={submitting}>
          Cancel
        </button>
      </div>
      {error && <p className="status error" style={{ marginTop: "0.75rem", marginBottom: 0 }}>{error}</p>}
      {status && <p className="quick-alert-status">{status}</p>}
    </form>
  );
}
