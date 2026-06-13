import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchLiveTradingSyncPreview, syncLiveTradingScreeners } from "../api";
import type { SyncPreviewItem, SyncPreviewSection } from "../types/liveTrading";
import SymbolLink from "./SymbolLink";

function itemKey(item: SyncPreviewItem): string {
  return `${item.symbol}:${item.source}`;
}

interface SyncScreenerPanelProps {
  onClose: () => void;
  onSynced: (message: string) => void;
}

export default function SyncScreenerPanel({ onClose, onSynced }: SyncScreenerPanelProps) {
  const [sections, setSections] = useState<SyncPreviewSection[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetchLiveTradingSyncPreview()
      .then((data) => {
        setSections(data.sections);
        const keys = new Set<string>();
        for (const sec of data.sections) {
          for (const item of sec.items) {
            keys.add(itemKey(item));
          }
        }
        setSelected(keys);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Failed to load screener stocks");
      })
      .finally(() => setLoading(false));
  }, []);

  const allKeys = useMemo(() => {
    const keys: string[] = [];
    for (const sec of sections) {
      for (const item of sec.items) {
        keys.push(itemKey(item));
      }
    }
    return keys;
  }, [sections]);

  const selectedCount = selected.size;
  const totalCount = allKeys.length;

  const toggleOne = useCallback((key: string, include: boolean) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (include) next.add(key);
      else next.delete(key);
      return next;
    });
  }, []);

  const toggleSection = useCallback((sec: SyncPreviewSection, include: boolean) => {
    setSelected((prev) => {
      const next = new Set(prev);
      for (const item of sec.items) {
        const key = itemKey(item);
        if (include) next.add(key);
        else next.delete(key);
      }
      return next;
    });
  }, []);

  const handleConfirm = async () => {
    setSyncing(true);
    setError(null);
    const excluded = allKeys
      .filter((key) => !selected.has(key))
      .map((key) => {
        const idx = key.indexOf(":");
        return { symbol: key.slice(0, idx), source: key.slice(idx + 1) };
      });
    try {
      const result = await syncLiveTradingScreeners({ excluded });
      if (result.synced_from.length === 0 && result.candidates_added === 0) {
        onSynced(result.message ?? "No screener results found.");
      } else {
        const parts: string[] = [];
        if (result.candidates_added > 0) {
          parts.push(`added ${result.candidates_added}`);
        }
        if (result.candidates_removed && result.candidates_removed > 0) {
          parts.push(`removed ${result.candidates_removed}`);
        }
        const labels = result.synced_from.map((s) => s.replace(/_/g, " ")).join(", ");
        onSynced(
          `Sync complete (${labels}): ${parts.join(", ")}. ` +
            (result.candidates_added > 0
              ? "One summary email sent for new candidates."
              : ""),
        );
      }
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sync failed");
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div className="lt-sync-overlay" role="dialog" aria-labelledby="lt-sync-title">
      <div className="lt-sync-panel filters-panel generic-filters-panel">
        <div className="lt-sync-panel-header">
          <div>
            <h2 id="lt-sync-title" className="filters-panel-title">
              Sync from Screeners
            </h2>
            <p className="lt-sync-panel-sub">
              Uncheck stocks to exclude. Selected stocks become candidates; excluded ones are
              removed from the watchlist. One email is sent after sync (not per stock).
            </p>
          </div>
          <button type="button" className="toolbar-btn" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>

        {loading && <p className="scan-meta">Loading screener results…</p>}
        {error && <div className="status error">{error}</div>}

        {!loading && !error && sections.length === 0 && (
          <p className="lt-empty">No screener results in database. Run a scan first.</p>
        )}

        {!loading && sections.length > 0 && (
          <>
            <div className="lt-sync-toolbar-row toolbar-row">
              <span className="scan-meta">
                {selectedCount} of {totalCount} selected
              </span>
              <div className="toolbar-right">
                <button
                  type="button"
                  className="toolbar-btn"
                  onClick={() => setSelected(new Set(allKeys))}
                >
                  Select all
                </button>
                <button
                  type="button"
                  className="toolbar-btn"
                  onClick={() => setSelected(new Set())}
                >
                  Deselect all
                </button>
              </div>
            </div>

            <div className="lt-sync-sections">
              {sections.map((sec) => {
                const secKeys = sec.items.map(itemKey);
                const secSelected = secKeys.filter((k) => selected.has(k)).length;
                const allSecSelected = secSelected === secKeys.length;
                return (
                  <div key={sec.source} className="lt-sync-section">
                    <div className="lt-sync-section-head">
                      <h3>
                        {sec.label}{" "}
                        <span className="scan-meta">
                          ({secSelected}/{sec.count})
                        </span>
                      </h3>
                      <button
                        type="button"
                        className="toolbar-btn"
                        onClick={() => toggleSection(sec, !allSecSelected)}
                      >
                        {allSecSelected ? "Deselect section" : "Select section"}
                      </button>
                    </div>
                    <ul className="lt-sync-stock-list">
                      {sec.items.map((item) => {
                        const key = itemKey(item);
                        const checked = selected.has(key);
                        return (
                          <li
                            key={key}
                            className={`lt-sync-stock-row${checked ? "" : " lt-sync-stock-excluded"}`}
                          >
                            <label className="lt-sync-stock-check">
                              <input
                                type="checkbox"
                                checked={checked}
                                onChange={(e) => toggleOne(key, e.target.checked)}
                              />
                              <span className="lt-sync-stock-symbol">
                                <SymbolLink symbol={item.symbol} />
                              </span>
                              <span className="lt-sync-stock-name">{item.company_name}</span>
                              {item.is_candidate && (
                                <span className="lt-sync-badge-existing">already candidate</span>
                              )}
                            </label>
                            <div className="lt-sync-stock-meta">
                              <span>Ref ₹{item.resistance.toLocaleString("en-IN")}</span>
                              {item.price != null && (
                                <span>Last ₹{item.price.toLocaleString("en-IN")}</span>
                              )}
                            </div>
                            <p className="lt-sync-stock-entry">
                              <strong>Entry:</strong> {item.entry_point}
                            </p>
                            <ul className="lt-candidate-bullets">
                              {item.bullets.map((b) => (
                                <li key={b}>{b}</li>
                              ))}
                            </ul>
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                );
              })}
            </div>

            <div className="lt-sync-actions toolbar-row">
              <button type="button" className="toolbar-btn" onClick={onClose} disabled={syncing}>
                Cancel
              </button>
              <button
                type="button"
                className="btn-primary toolbar-btn"
                disabled={syncing || selectedCount === 0}
                onClick={handleConfirm}
              >
                {syncing ? "Syncing…" : `Sync ${selectedCount} stock(s)`}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
