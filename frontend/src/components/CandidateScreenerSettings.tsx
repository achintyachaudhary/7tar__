import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  fetchLiveTradingSyncPreview,
  fetchWidgetPreferences,
  syncLiveTradingScreeners,
  updateWidgetPreferences,
} from "../api";
import type { SyncPreviewItem, SyncPreviewSection } from "../types/liveTrading";
import { writeLocalCache } from "../lib/dbFirstStorage";
import type { ScreenerSyncPrefs, WidgetPreferences } from "../types/widgetPreferences";
import SymbolLink from "./SymbolLink";

const SCREENER_SYNC_WIDGET_ID = "live-trades-screener-sync";
const SCREENER_SYNC_CACHE_SUFFIX = `widget_prefs:${SCREENER_SYNC_WIDGET_ID}`;

function itemKey(item: SyncPreviewItem): string {
  return `${item.symbol}:${item.source}`;
}

function buildExcluded(
  sections: SyncPreviewSection[],
  enabledScreeners: Set<string>,
  selectedStocks: Set<string>,
): { symbol: string; source: string }[] {
  const excluded: { symbol: string; source: string }[] = [];
  for (const sec of sections) {
    if (!enabledScreeners.has(sec.source)) continue;
    for (const item of sec.items) {
      const key = itemKey(item);
      if (!selectedStocks.has(key)) {
        const idx = key.indexOf(":");
        excluded.push({
          symbol: key.slice(0, idx),
          source: key.slice(idx + 1),
        });
      }
    }
  }
  return excluded;
}

function applySavedPrefs(
  sections: SyncPreviewSection[],
  filters: Record<string, unknown>,
): { enabled: Set<string>; selected: Set<string> } {
  const allScreeners = new Set(sections.map((s) => s.source));
  const saved = filters as Partial<ScreenerSyncPrefs>;
  const hasPrefs =
    saved.enabled_screeners !== undefined || saved.excluded_stocks !== undefined;

  if (!hasPrefs) {
    const selected = new Set<string>();
    for (const sec of sections) {
      for (const item of sec.items) selected.add(itemKey(item));
    }
    return { enabled: allScreeners, selected };
  }

  const enabled = new Set(
    (saved.enabled_screeners ?? []).filter((s) => allScreeners.has(s)),
  );
  const excludedSet = new Set(
    (saved.excluded_stocks ?? []).map((e) => `${e.symbol}:${e.source}`),
  );
  const selected = new Set<string>();
  for (const sec of sections) {
    if (!enabled.has(sec.source)) continue;
    for (const item of sec.items) {
      const key = itemKey(item);
      if (!excludedSet.has(key)) selected.add(key);
    }
  }
  return { enabled, selected };
}

function prefsFromState(
  enabledScreeners: Set<string>,
  sections: SyncPreviewSection[],
  selectedStocks: Set<string>,
): ScreenerSyncPrefs {
  return {
    enabled_screeners: Array.from(enabledScreeners),
    excluded_stocks: buildExcluded(sections, enabledScreeners, selectedStocks),
  };
}

interface CandidateScreenerSettingsProps {
  onClose: () => void;
  onSynced: (message: string) => void;
}

export default function CandidateScreenerSettings({
  onClose,
  onSynced,
}: CandidateScreenerSettingsProps) {
  const [sections, setSections] = useState<SyncPreviewSection[]>([]);
  const [watchlistCount, setWatchlistCount] = useState(0);
  const [enabledScreeners, setEnabledScreeners] = useState<Set<string>>(new Set());
  const [selectedStocks, setSelectedStocks] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const prefsReadyRef = useRef(false);
  const saveTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const persistPrefs = useCallback(
    async (enabled: Set<string>, selected: Set<string>, secs: SyncPreviewSection[]) => {
      const column_filters = prefsFromState(enabled, secs, selected);
      await updateWidgetPreferences(SCREENER_SYNC_WIDGET_ID, { column_filters });
      const snapshot: WidgetPreferences = {
        widget_id: SCREENER_SYNC_WIDGET_ID,
        search_term: "",
        visible_columns: [],
        column_filters,
      };
      writeLocalCache(SCREENER_SYNC_CACHE_SUFFIX, snapshot);
    },
    [],
  );

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    setError(null);
    prefsReadyRef.current = false;

    Promise.all([
      fetchLiveTradingSyncPreview(),
      fetchWidgetPreferences(SCREENER_SYNC_WIDGET_ID),
    ])
      .then(([preview, prefs]) => {
        if (!mounted) return;
        setSections(preview.sections);
        setWatchlistCount(preview.watchlist_count ?? 0);
        const { enabled, selected } = applySavedPrefs(
          preview.sections,
          prefs.column_filters ?? {},
        );
        setEnabledScreeners(enabled);
        setSelectedStocks(selected);
        writeLocalCache(SCREENER_SYNC_CACHE_SUFFIX, prefs);
        prefsReadyRef.current = true;
      })
      .catch((err) => {
        if (!mounted) return;
        setError(err instanceof Error ? err.message : "Failed to load screeners");
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });

    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (loading || !prefsReadyRef.current || sections.length === 0) return;

    if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current);
    saveTimeoutRef.current = setTimeout(() => {
      persistPrefs(enabledScreeners, selectedStocks, sections).catch((err) => {
        console.error("Failed to save screener sync settings:", err);
      });
    }, 800);

    return () => {
      if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current);
    };
  }, [enabledScreeners, selectedStocks, sections, loading, persistPrefs]);

  const visibleSections = useMemo(
    () => sections.filter((s) => enabledScreeners.has(s.source)),
    [sections, enabledScreeners],
  );

  const selectedToSyncCount = useMemo(() => {
    let n = 0;
    for (const sec of sections) {
      if (!enabledScreeners.has(sec.source)) continue;
      for (const item of sec.items) {
        if (selectedStocks.has(itemKey(item))) n += 1;
      }
    }
    return n;
  }, [sections, enabledScreeners, selectedStocks]);

  const cacheTotal = useMemo(
    () => sections.reduce((sum, sec) => sum + sec.count, 0),
    [sections],
  );

  const toggleScreener = useCallback((source: string, enabled: boolean) => {
    setEnabledScreeners((prev) => {
      const next = new Set(prev);
      if (enabled) next.add(source);
      else next.delete(source);
      return next;
    });
    const sec = sections.find((s) => s.source === source);
    if (!sec) return;
    setSelectedStocks((prev) => {
      const next = new Set(prev);
      for (const item of sec.items) {
        const key = itemKey(item);
        if (enabled) next.add(key);
        else next.delete(key);
      }
      return next;
    });
  }, [sections]);

  const toggleStock = useCallback((key: string, include: boolean) => {
    setSelectedStocks((prev) => {
      const next = new Set(prev);
      if (include) next.add(key);
      else next.delete(key);
      return next;
    });
  }, []);

  const handleClose = useCallback(() => {
    if (saveTimeoutRef.current) {
      clearTimeout(saveTimeoutRef.current);
      saveTimeoutRef.current = null;
    }
    if (prefsReadyRef.current && sections.length > 0) {
      persistPrefs(enabledScreeners, selectedStocks, sections).catch((err) => {
        console.error("Failed to save screener sync settings:", err);
      });
    }
    onClose();
  }, [enabledScreeners, selectedStocks, sections, onClose, persistPrefs]);

  const handleSync = async () => {
    if (enabledScreeners.size === 0) {
      setError("Select at least one screener.");
      return;
    }
    setSyncing(true);
    setError(null);

    const excluded = buildExcluded(sections, enabledScreeners, selectedStocks);

    try {
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current);
        saveTimeoutRef.current = null;
      }
      await persistPrefs(enabledScreeners, selectedStocks, sections);

      const result = await syncLiveTradingScreeners({
        scanTypes: Array.from(enabledScreeners),
        excluded,
      });
      const parts: string[] = [];
      if (result.candidates_added > 0) parts.push(`added ${result.candidates_added}`);
      if (result.candidates_removed && result.candidates_removed > 0) {
        parts.push(`removed ${result.candidates_removed}`);
      }
      const labels = result.synced_from.map((s) => s.replace(/_/g, " ")).join(", ");
      onSynced(
        parts.length > 0
          ? `Synced from ${labels}: ${parts.join(", ")}. One summary email for new candidates.`
          : result.message ?? "Sync complete.",
      );
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sync failed");
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div className="lt-screener-settings filters-panel generic-filters-panel">
      <div className="lt-screener-settings-head">
        <h3 className="filters-panel-title">Screener sync settings</h3>
        <button type="button" className="toolbar-btn" onClick={handleClose} aria-label="Close">
          ✕
        </button>
      </div>
      <p className="lt-sync-panel-sub">
        Choose which screeners to sync. Uncheck a screener to drop its stocks from candidates.
        Uncheck individual stocks below. One consolidated email is sent after sync.
      </p>
      {!loading && sections.length > 0 && (
        <p className="lt-sync-count-summary scan-meta">
          Watchlist now: <strong>{watchlistCount}</strong>
          {" · "}
          Selected here: <strong>{selectedToSyncCount}</strong>
          {" · "}
          In scan caches: <strong>{cacheTotal}</strong>
          {watchlistCount > selectedToSyncCount && (
            <>
              {" "}
              — watchlist can exceed your selection until you click Apply &amp; sync (stale
              rows are removed then).
            </>
          )}
        </p>
      )}

      {loading && <p className="scan-meta">Loading…</p>}
      {error && <div className="status error">{error}</div>}

      {!loading && sections.length === 0 && (
        <p className="lt-empty">No screener results. Run a scan on Stock Finder tabs first.</p>
      )}

      {!loading && sections.length > 0 && (
        <>
          <div className="lt-screener-picks">
            <p className="toolbar-label">Screeners</p>
            <div className="lt-screener-pick-grid">
              {sections.map((sec) => {
                const on = enabledScreeners.has(sec.source);
                return (
                  <label key={sec.source} className={`lt-screener-pick${on ? " on" : ""}`}>
                    <input
                      type="checkbox"
                      checked={on}
                      onChange={(e) => toggleScreener(sec.source, e.target.checked)}
                    />
                    <span className="lt-screener-pick-label">{sec.label}</span>
                    <span className="lt-screener-pick-count">
                      {sec.count} in scan
                      {sec.watchlist_count != null && sec.watchlist_count !== sec.count && (
                        <> · {sec.watchlist_count} in watchlist</>
                      )}
                    </span>
                  </label>
                );
              })}
            </div>
          </div>

          {visibleSections.map((sec) => {
            const secKeys = sec.items.map(itemKey);
            const picked = secKeys.filter((k) => selectedStocks.has(k)).length;
            return (
              <div key={sec.source} className="lt-sync-section">
                <div className="lt-sync-section-head">
                  <h4>
                    {sec.label}{" "}
                    <span className="scan-meta">
                      ({picked}/{sec.count})
                    </span>
                  </h4>
                  <button
                    type="button"
                    className="toolbar-btn"
                    onClick={() => {
                      const allOn = picked === secKeys.length;
                      setSelectedStocks((prev) => {
                        const next = new Set(prev);
                        for (const item of sec.items) {
                          const key = itemKey(item);
                          if (allOn) next.delete(key);
                          else next.add(key);
                        }
                        return next;
                      });
                    }}
                  >
                    {picked === secKeys.length ? "Deselect all" : "Select all"}
                  </button>
                </div>
                <ul className="lt-sync-stock-list lt-sync-stock-list-compact">
                  {sec.items.map((item) => {
                    const key = itemKey(item);
                    const checked = selectedStocks.has(key);
                    return (
                      <li
                        key={key}
                        className={`lt-sync-stock-row${checked ? "" : " lt-sync-stock-excluded"}`}
                      >
                        <label className="lt-sync-stock-check">
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={(e) => toggleStock(key, e.target.checked)}
                          />
                          <span className="lt-sync-stock-symbol">
                            <SymbolLink symbol={item.symbol} />
                          </span>
                          {item.is_candidate && (
                            <span className="lt-sync-badge-existing">in list</span>
                          )}
                        </label>
                      </li>
                    );
                  })}
                </ul>
              </div>
            );
          })}

          <div className="lt-sync-actions toolbar-row">
            <button type="button" className="toolbar-btn" onClick={handleClose} disabled={syncing}>
              Cancel
            </button>
            <button
              type="button"
              className="btn-primary toolbar-btn"
              disabled={syncing || enabledScreeners.size === 0}
              onClick={handleSync}
            >
              {syncing ? "Syncing…" : "Apply & sync"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
