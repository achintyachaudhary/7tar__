import { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchDayScanTable,
} from "../api";
import SortableTh from "./SortableTh";
import SymbolLink from "./SymbolLink";
import DayScanChartModal from "./DayScanChartModal";
import StockDetailModal from "./StockDetailModal";
import ColumnVisibilityControl, { ColumnDefinition } from "./ColumnVisibilityControl";
import { useTableSort } from "../hooks/useTableSort";
import { useWidgetPreferences } from "../hooks/useWidgetPreferences";
import { useDayScanSync } from "../context/DayScanSyncContext";
import type { DayScanRow } from "../types/dayScan";
import type { SelectedStock } from "../types";
import { formatIST } from "../lib/formatTime";
import TimestampLabel from "./TimestampLabel";

function fmtPct(v: number | null | undefined): string {
  if (v == null) return "—";
  const sign = v > 0 ? "+" : "";
  return `${sign}${v.toFixed(2)}%`;
}

function fmtNum(v: number | null | undefined, decimals = 2): string {
  if (v == null) return "—";
  return v.toLocaleString("en-IN", { maximumFractionDigits: decimals });
}

function pctClass(v: number | null | undefined): string {
  if (v == null) return "";
  if (v > 0) return "positive";
  if (v < 0) return "negative";
  return "";
}

function formatSyncDate(dateStr: string | null): string {
  if (!dateStr) return "—";
  const d = new Date(`${dateStr}T00:00:00`);
  return d.toLocaleDateString("en-IN", {
    timeZone: "Asia/Kolkata",
    dateStyle: "medium",
  });
}

function getSortValue(row: DayScanRow, key: string): string | number | null {
  switch (key) {
    case "symbol":
      return row.symbol;
    case "company_name":
      return row.company_name;
    case "industry":
      return row.industry;
    case "market_cap_cr":
      return row.market_cap_cr;
    case "pe_ratio":
      return row.pe_ratio;
    case "roce_pct":
      return row.roce_pct;
    case "return_1d_pct":
      return row.return_1d_pct;
    case "return_1w_pct":
      return row.return_1w_pct;
    case "return_1m_pct":
      return row.return_1m_pct;
    case "return_1y_pct":
      return row.return_1y_pct;
    case "updated_at":
      return row.updated_at;
    default:
      return null;
  }
}

const DAY_SCAN_COLUMNS: ColumnDefinition[] = [
  { key: "symbol", label: "Symbol", alwaysVisible: true },
  { key: "company_name", label: "Company", alwaysVisible: true },
  { key: "return_1d_pct", label: "1D %", alwaysVisible: false },
  { key: "return_1w_pct", label: "1W %", alwaysVisible: false },
  { key: "return_1m_pct", label: "1M %", alwaysVisible: false },
  { key: "return_1y_pct", label: "1Y %", alwaysVisible: false },
  { key: "industry", label: "Industry", alwaysVisible: false },
  { key: "market_cap_cr", label: "Mkt Cap (Cr)", alwaysVisible: false },
  { key: "pe_ratio", label: "P/E", alwaysVisible: false },
  { key: "roce_pct", label: "ROCE %", alwaysVisible: false },
  { key: "updated_at", label: "Updated", alwaysVisible: false },
];

const DEFAULT_VISIBLE_COLUMNS = DAY_SCAN_COLUMNS.map((c) => c.key);

interface DayScanTableProps {
  onFetch?: () => void;
  fetchTrigger?: number;
}

export default function DayScanTable({ onFetch, fetchTrigger }: DayScanTableProps) {
  const [rows, setRows] = useState<DayScanRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tableFetchedAt, setTableFetchedAt] = useState<Date | null>(null);
  const [chartStock, setChartStock] = useState<DayScanRow | null>(null);
  const [selectedStock, setSelectedStock] = useState<SelectedStock | null>(null);

  const {
    syncThroughDate,
    expectedThroughDate,
    lastSyncAt,
    needsSync,
    syncing,
    job,
    error: syncError,
    refreshCounter,
    startSync,
  } = useDayScanSync();

  const {
    preferences,
    setSearchTerm,
    setVisibleColumns,
  } = useWidgetPreferences("day_scan_table", DEFAULT_VISIBLE_COLUMNS);

  const loadTable = useCallback(async () => {
    try {
      const data = await fetchDayScanTable();
      setRows(data.rows);
      setTableFetchedAt(new Date());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load day scan data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadTable();
  }, [loadTable, fetchTrigger, refreshCounter]);

  const filteredRows = useMemo(() => {
    if (!preferences.search_term.trim()) return rows;
    const term = preferences.search_term.toLowerCase();
    return rows.filter(
      (row) =>
        row.symbol.toLowerCase().includes(term) ||
        row.company_name.toLowerCase().includes(term) ||
        row.industry?.toLowerCase().includes(term),
    );
  }, [rows, preferences.search_term]);

  const { sortedRows, sortKey, sortDir, toggleSort } = useTableSort(
    filteredRows,
    "return_1d_pct",
    "desc",
    getSortValue,
  );

  const isColumnVisible = useCallback(
    (columnKey: string) => preferences.visible_columns.includes(columnKey),
    [preferences.visible_columns],
  );

  const openRow = (row: DayScanRow) => {
    setSelectedStock({
      symbol: row.symbol,
      label: row.company_name,
    });
  };

  const handleFetch = () => {
    setError(null);
    startSync(true);
    onFetch?.();
  };

  const progressPct =
    job && job.total > 0 ? Math.round((job.processed / job.total) * 100) : 0;

  const isUpToDate =
    syncThroughDate &&
    expectedThroughDate &&
    syncThroughDate >= expectedThroughDate &&
    !needsSync;

  const liveProgressPct = syncing
    ? progressPct
    : isUpToDate || lastSyncAt
      ? 100
      : 0;

  const displayError = error || syncError;

  return (
    <section className="day-scan-section">
      <div className="tab-toolbar day-scan-toolbar">
        <div>
          <h1 className="day-scan-page-title">NSE Stocks</h1>
          <p className="meta day-scan-page-meta">
            Daily NSE prices and fundamentals — auto-syncs through the previous trading day
          </p>
        </div>
        <div className="day-scan-header-actions">
          <button
            type="button"
            onClick={handleFetch}
            disabled={syncing}
            className="toolbar-btn sync-icon-btn"
            title="Sync all NSE stocks"
          >
            {syncing ? "⟳" : "↻"}
          </button>
        </div>
      </div>

      <div className="scan-live-status">
        <div className="scan-live-status-header">
          <div className="scan-live-status-label">
            {syncing ? (
              <span className="scan-live-status-active">● Syncing NSE Stocks data…</span>
            ) : displayError ? (
              <span className="scan-live-status-error">⚠ Sync interrupted</span>
            ) : lastSyncAt ? (
              <span className="scan-live-status-done">
                ✓ Last synced: {formatIST(lastSyncAt)}
              </span>
            ) : (
              <span className="scan-live-status-idle">Waiting for first sync…</span>
            )}
          </div>
          {syncing && job && (
            <div className="scan-live-status-counter">
              Processed <strong>{job.processed}</strong> / {job.total} stocks
            </div>
          )}
        </div>

        <div className="scan-live-status-bar-track">
          <div
            className="scan-live-status-bar-fill"
            style={{ width: `${liveProgressPct}%` }}
          />
        </div>

        <div className="scan-live-status-footer">
          <div>
            {syncing && job?.current_symbol ? (
              <>Currently syncing: <strong>{job.current_symbol}</strong></>
            ) : isUpToDate && syncThroughDate ? (
              <>Synced through: <strong>{formatSyncDate(syncThroughDate)}</strong></>
            ) : needsSync ? (
              <>Expected through: <strong>{formatSyncDate(expectedThroughDate)}</strong></>
            ) : (
              "All profiles processed"
            )}
          </div>
          <div>{liveProgressPct}%</div>
        </div>

        {displayError && (
          <div className="scan-live-status-error-box">{displayError}</div>
        )}
      </div>

      <p className="meta day-scan-count-meta">
        {rows.length > 0
          ? `${filteredRows.length} of ${rows.length} stocks ${preferences.search_term ? "(filtered)" : ""}`
          : "No scan data yet — click Fetch All Stocks to load"}
        {tableFetchedAt && (
          <>
            {" · "}
            <TimestampLabel at={tableFetchedAt} label="Table loaded" />
          </>
        )}
      </p>

      {!loading && rows.length > 0 && (
        <div className="day-scan-controls">
          <input
            type="text"
            placeholder="Search stocks by symbol, name, or industry..."
            value={preferences.search_term}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="day-scan-search"
          />
          <ColumnVisibilityControl
            columns={DAY_SCAN_COLUMNS}
            visibleColumns={preferences.visible_columns}
            onVisibleColumnsChange={setVisibleColumns}
          />
        </div>
      )}

      {loading ? (
        <div className="status loading">Loading NSE Stocks table…</div>
      ) : sortedRows.length === 0 ? (
        <div className="status">No stocks in database yet. Click Fetch All Stocks to begin.</div>
      ) : (
        <div className="table-wrap day-scan-table-wrap">
          <table className="stock-table day-scan-table">
            <thead>
              <tr>
                {isColumnVisible("symbol") && (
                  <SortableTh label="Symbol" sortKey="symbol" activeKey={sortKey} direction={sortDir} onSort={toggleSort} />
                )}
                {isColumnVisible("company_name") && (
                  <SortableTh label="Company" sortKey="company_name" activeKey={sortKey} direction={sortDir} onSort={toggleSort} />
                )}
                {isColumnVisible("return_1d_pct") && (
                  <SortableTh label="1D %" sortKey="return_1d_pct" activeKey={sortKey} direction={sortDir} onSort={toggleSort} />
                )}
                {isColumnVisible("return_1w_pct") && (
                  <SortableTh label="1W %" sortKey="return_1w_pct" activeKey={sortKey} direction={sortDir} onSort={toggleSort} />
                )}
                {isColumnVisible("return_1m_pct") && (
                  <SortableTh label="1M %" sortKey="return_1m_pct" activeKey={sortKey} direction={sortDir} onSort={toggleSort} />
                )}
                {isColumnVisible("return_1y_pct") && (
                  <SortableTh label="1Y %" sortKey="return_1y_pct" activeKey={sortKey} direction={sortDir} onSort={toggleSort} />
                )}
                {isColumnVisible("industry") && (
                  <SortableTh label="Industry" sortKey="industry" activeKey={sortKey} direction={sortDir} onSort={toggleSort} />
                )}
                {isColumnVisible("market_cap_cr") && (
                  <SortableTh label="Mkt Cap (Cr)" sortKey="market_cap_cr" activeKey={sortKey} direction={sortDir} onSort={toggleSort} />
                )}
                {isColumnVisible("pe_ratio") && (
                  <SortableTh label="P/E" sortKey="pe_ratio" activeKey={sortKey} direction={sortDir} onSort={toggleSort} />
                )}
                {isColumnVisible("roce_pct") && (
                  <SortableTh label="ROCE %" sortKey="roce_pct" activeKey={sortKey} direction={sortDir} onSort={toggleSort} />
                )}
                {isColumnVisible("updated_at") && (
                  <SortableTh label="Updated" sortKey="updated_at" activeKey={sortKey} direction={sortDir} onSort={toggleSort} />
                )}
                <th className="day-scan-chart-col">Chart</th>
              </tr>
            </thead>
            <tbody>
              {sortedRows.map((row) => (
                <tr
                  key={row.symbol}
                  className="clickable-row"
                  onClick={() => openRow(row)}
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      openRow(row);
                    }
                  }}
                  role="button"
                  aria-label={`View details for ${row.symbol}`}
                >
                  {isColumnVisible("symbol") && (
                    <td onClick={(e) => e.stopPropagation()}>
                      <SymbolLink symbol={row.symbol} />
                    </td>
                  )}
                  {isColumnVisible("company_name") && (
                    <td className="company-cell">{row.company_name}</td>
                  )}
                  {isColumnVisible("return_1d_pct") && (
                    <td className={pctClass(row.return_1d_pct)}>{fmtPct(row.return_1d_pct)}</td>
                  )}
                  {isColumnVisible("return_1w_pct") && (
                    <td className={pctClass(row.return_1w_pct)}>{fmtPct(row.return_1w_pct)}</td>
                  )}
                  {isColumnVisible("return_1m_pct") && (
                    <td className={pctClass(row.return_1m_pct)}>{fmtPct(row.return_1m_pct)}</td>
                  )}
                  {isColumnVisible("return_1y_pct") && (
                    <td className={pctClass(row.return_1y_pct)}>{fmtPct(row.return_1y_pct)}</td>
                  )}
                  {isColumnVisible("industry") && <td>{row.industry ?? "—"}</td>}
                  {isColumnVisible("market_cap_cr") && <td>{fmtNum(row.market_cap_cr, 0)}</td>}
                  {isColumnVisible("pe_ratio") && <td>{fmtNum(row.pe_ratio)}</td>}
                  {isColumnVisible("roce_pct") && (
                    <td>{row.roce_pct != null ? `${row.roce_pct.toFixed(2)}%` : "—"}</td>
                  )}
                  {isColumnVisible("updated_at") && (
                    <td className="lt-date-cell">{formatIST(row.updated_at)}</td>
                  )}
                  <td className="day-scan-chart-col" onClick={(e) => e.stopPropagation()}>
                    <div className="day-scan-chart-actions">
                      <button
                        type="button"
                        className="toolbar-btn day-scan-db-chart-btn"
                        onClick={() => setChartStock(row)}
                        title="View stored price history chart"
                      >
                        History
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {chartStock && (
        <DayScanChartModal stock={chartStock} onClose={() => setChartStock(null)} />
      )}

      <StockDetailModal stock={selectedStock} onClose={() => setSelectedStock(null)} />
    </section>
  );
}
