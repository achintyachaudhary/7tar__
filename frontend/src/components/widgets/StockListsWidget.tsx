import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchStockListsTable } from "../../api";
import { useStockLists } from "../../context/StockListsContext";
import type { EnrichedStockListRow, StockListFilter } from "../../types/stockListTable";
import { parseSymbolLines } from "../../types/stockLists";
import { useNseSessionOpen } from "../../lib/nseSession";
import {
  freshQuote,
  livePct,
  useLiveTicks,
  useWatchSymbols,
} from "../../context/LiveTicksContext";
import StockListActions from "../StockListActions";
import SymbolLink from "../SymbolLink";
import { displaySymbol } from "../../utils/tradingView";

interface Props {
  size: "sm" | "md" | "lg";
}

const FILTERS: { id: StockListFilter; label: string; icon: string }[] = [
  { id: "all", label: "All", icon: "☰" },
  { id: "favorite", label: "Favorite", icon: "★" },
  { id: "fishy", label: "Fishy", icon: "🐟" },
  { id: "blacklist", label: "Blacklist", icon: "⛔" },
];

function fmtCap(v: number | null | undefined): string {
  if (v == null) return "—";
  if (v >= 100_000) return `₹${(v / 100_000).toFixed(2)}L Cr`;
  if (v >= 1000) return `₹${(v / 1000).toFixed(1)}k Cr`;
  return `₹${Math.round(v)} Cr`;
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

function TagBadges({ tags }: { tags: EnrichedStockListRow["tags"] }) {
  return (
    <span className="sl-table-tags">
      {tags.includes("favorite") && (
        <span className="sl-table-tag sl-table-tag-fav" title="Favorite">
          ★
        </span>
      )}
      {tags.includes("fishy") && (
        <span className="sl-table-tag sl-table-tag-fishy" title="Fishy">
          🐟
        </span>
      )}
      {tags.includes("blacklist") && (
        <span className="sl-table-tag sl-table-tag-block" title="Blacklisted">
          ⛔
        </span>
      )}
    </span>
  );
}

export default function StockListsWidget({ size }: Props) {
  const nseOpen = useNseSessionOpen();
  const {
    favorites,
    fishy,
    blacklist,
    loading: listsLoading,
    saveLists,
  } = useStockLists();
  const [rows, setRows] = useState<EnrichedStockListRow[]>([]);
  const [tableLoading, setTableLoading] = useState(true);
  const [filter, setFilter] = useState<StockListFilter>("all");
  const [favText, setFavText] = useState("");
  const [blText, setBlText] = useState("");
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [refreshedAt, setRefreshedAt] = useState<Date | null>(null);

  const loadTable = useCallback(async (silent = false) => {
    if (!silent) setTableLoading(true);
    try {
      const data = await fetchStockListsTable();
      setRows(data.rows);
      setRefreshedAt(new Date());
    } catch {
      if (!silent) setRows([]);
    } finally {
      if (!silent) setTableLoading(false);
    }
  }, []);

  useEffect(() => {
    setFavText(favorites.map((f) => displaySymbol(f.symbol)).join("\n"));
    setBlText(blacklist.map((b) => displaySymbol(b.symbol)).join("\n"));
  }, [favorites, blacklist]);

  useEffect(() => {
    void loadTable();
    const intervalMs = nseOpen ? 30_000 : 60_000;
    const id = window.setInterval(() => void loadTable(true), intervalMs);
    return () => window.clearInterval(id);
  }, [loadTable, nseOpen]);

  useEffect(() => {
    void loadTable(true);
  }, [favorites.length, fishy.length, blacklist.length, loadTable]);

  // Stream displayed symbols; overlay LTP + today's % from live ticks (~3s).
  const watchedSymbols = useMemo(() => rows.map((r) => r.symbol), [rows]);
  useWatchSymbols(watchedSymbols);
  const { quotes } = useLiveTicks();

  const liveRows = useMemo(() => {
    return rows.map((r) => {
      const q = freshQuote(quotes, r.symbol);
      if (!q || q.price === r.ltp) return r;
      return {
        ...r,
        ltp: q.price,
        change_day_pct: livePct(q.price, r.ltp, r.change_day_pct) ?? r.change_day_pct,
      };
    });
  }, [rows, quotes]);

  const filteredRows = useMemo(() => {
    if (filter === "all") return liveRows;
    return liveRows.filter((r) => r.tags.includes(filter));
  }, [liveRows, filter]);

  const handleSave = async () => {
    setSaving(true);
    setStatus(null);
    try {
      await saveLists(parseSymbolLines(favText), parseSymbolLines(blText));
      setStatus("Saved.");
      await loadTable(true);
    } catch (err) {
      setStatus(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  if (listsLoading && tableLoading && rows.length === 0) {
    return <div className="widget-loading">Loading watchlists…</div>;
  }

  const maxRows = size === "sm" ? 8 : size === "md" ? 14 : 24;
  const displayRows = filteredRows.slice(0, maxRows);

  return (
    <div className="stock-lists-widget sl-table-widget">
      <div className="sl-table-toolbar">
        <div className="sl-table-filters">
          {FILTERS.map((f) => (
            <button
              key={f.id}
              type="button"
              className={`sl-table-filter${filter === f.id ? " active" : ""}`}
              onClick={() => setFilter(f.id)}
            >
              <span aria-hidden="true">{f.icon}</span> {f.label}
            </button>
          ))}
        </div>
        <button
          type="button"
          className="toolbar-btn sl-table-refresh"
          onClick={() => void loadTable()}
          disabled={tableLoading}
          title="Refresh quotes"
        >
          {tableLoading ? "…" : "↻"}
        </button>
      </div>

      {filteredRows.length === 0 ? (
        <p className="sl-empty sl-table-empty">
          {filter === "all"
            ? "No stocks flagged yet — use ★ / 🐟 / ⛔ on any symbol."
            : `No ${filter} stocks.`}
        </p>
      ) : (
        <div className="sl-table-wrap">
          <table className="sl-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Tags</th>
                <th>LTP</th>
                <th>
                  Today %
                  {nseOpen && (
                    <span className="sl-table-live-hint" title="Live vs previous close">
                      {" "}
                      live
                    </span>
                  )}
                </th>
                <th>7D %</th>
                <th>Mkt cap</th>
                <th>Industry</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {displayRows.map((row) => (
                <tr key={row.symbol}>
                  <td className="sl-table-sym">
                    <SymbolLink symbol={row.symbol} showBadges={false} showListActions={false} />
                    {row.company_name &&
                      row.company_name !== displaySymbol(row.symbol) && (
                        <span className="sl-table-company">{row.company_name}</span>
                      )}
                  </td>
                  <td>
                    <TagBadges tags={row.tags} />
                  </td>
                  <td>
                    {row.ltp != null
                      ? `₹${row.ltp.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`
                      : "—"}
                  </td>
                  <td>
                    <PctCell value={row.change_day_pct} />
                  </td>
                  <td>
                    <PctCell value={row.change_7d_pct} />
                  </td>
                  <td>{fmtCap(row.market_cap_cr)}</td>
                  <td className="sl-table-industry">{row.industry ?? "—"}</td>
                  <td>
                    <StockListActions symbol={row.symbol} compact />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {filteredRows.length > maxRows && (
            <p className="meta sl-table-more">
              Showing {maxRows} of {filteredRows.length} — resize widget to Large for more rows.
            </p>
          )}
        </div>
      )}

      {refreshedAt && (
        <p className="meta sl-table-asof">
          {nseOpen ? "Live quotes" : "Quotes"} as of{" "}
          {refreshedAt.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}
          {nseOpen ? " · refreshes every 30s" : ""}
        </p>
      )}

      <details className="sl-editor">
        <summary>Bulk edit Favorites &amp; Blacklist</summary>
        <div className="sl-editor-grid">
          <label>
            <span className="stock-lists-widget-label">★ Favorites</span>
            <textarea
              className="stock-lists-textarea"
              rows={4}
              value={favText}
              onChange={(e) => setFavText(e.target.value)}
              placeholder={"RELIANCE\nTCS"}
            />
          </label>
          <label>
            <span className="stock-lists-widget-label">⛔ Blacklist</span>
            <textarea
              className="stock-lists-textarea stock-lists-textarea-blacklist"
              rows={4}
              value={blText}
              onChange={(e) => setBlText(e.target.value)}
              placeholder={"YESBANK"}
            />
          </label>
        </div>
        <div className="stock-lists-widget-footer">
          <button
            type="button"
            className="toolbar-btn btn-primary"
            disabled={saving}
            onClick={() => void handleSave()}
          >
            {saving ? "Saving…" : "Save lists"}
          </button>
          {status && <span className="meta">{status}</span>}
        </div>
      </details>
    </div>
  );
}
