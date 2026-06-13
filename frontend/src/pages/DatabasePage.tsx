import { useCallback, useEffect, useState } from "react";
import { fetchDbTableData, fetchDbTables } from "../api";
import type { DbTableMeta } from "../types/dayScan";
import StockAiDataPanel from "../components/StockAiDataPanel";

const PAGE_SIZE = 50;

type DbTab = "main" | "stock_ai";

export default function DatabasePage() {
  const [tab, setTab] = useState<DbTab>("main");
  const [tables, setTables] = useState<DbTableMeta[]>([]);
  const [selectedTable, setSelectedTable] = useState<string | null>(null);
  const [columns, setColumns] = useState<string[]>([]);
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [tableLoading, setTableLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchDbTables()
      .then((data) => {
        setTables(data.tables);
        if (data.tables.length > 0) {
          setSelectedTable(data.tables[0].name);
        }
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load tables"))
      .finally(() => setLoading(false));
  }, []);

  const loadTableData = useCallback(async (table: string, pageOffset: number) => {
    setTableLoading(true);
    try {
      const data = await fetchDbTableData(table, pageOffset, PAGE_SIZE);
      setColumns(data.columns);
      setRows(data.rows);
      setTotal(data.total);
      setOffset(data.offset);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load table data");
    } finally {
      setTableLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedTable) {
      loadTableData(selectedTable, 0);
    }
  }, [selectedTable, loadTableData]);

  const totalPages = Math.ceil(total / PAGE_SIZE);
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  return (
    <div className="page-container database-page">
      <div className="database-header">
        <h1 className="page-title">Database Explorer</h1>
        <p className="page-subtitle">
          Peek into stored time-series prices, day scan snapshots, and other tables
        </p>
      </div>

      <div className="database-tabs">
        <button
          type="button"
          className={`database-tab${tab === "main" ? " active" : ""}`}
          onClick={() => setTab("main")}
        >
          🗄️ Main App DB
        </button>
        <button
          type="button"
          className={`database-tab${tab === "stock_ai" ? " active" : ""}`}
          onClick={() => setTab("stock_ai")}
        >
          🤖 Stock AI — Vectors & DB
        </button>
      </div>

      {tab === "stock_ai" ? (
        <StockAiDataPanel />
      ) : loading ? (
        <div className="status loading">Loading database metadata…</div>
      ) : error ? (
        <div className="status error">{error}</div>
      ) : (
        <div className="database-layout">
          <aside className="database-sidebar">
            <div className="database-sidebar-title">Tables</div>
            <ul className="database-table-list">
              {tables.map((t) => (
                <li key={t.name}>
                  <button
                    type="button"
                    className={`database-table-btn${selectedTable === t.name ? " active" : ""}`}
                    onClick={() => {
                      setSelectedTable(t.name);
                      setOffset(0);
                    }}
                  >
                    <span className="database-table-name">{t.name}</span>
                    <span className="database-table-count">{t.row_count.toLocaleString()}</span>
                  </button>
                </li>
              ))}
            </ul>
          </aside>

          <main className="database-main">
            {selectedTable && (
              <>
                <div className="database-main-header">
                  <h2>{selectedTable}</h2>
                  <span className="meta">{total.toLocaleString()} rows</span>
                </div>

                {tableLoading ? (
                  <div className="status loading">Loading rows…</div>
                ) : (
                  <>
                    <div className="table-wrap database-table-wrap">
                      <table className="stock-table database-data-table">
                        <thead>
                          <tr>
                            {columns.map((col) => (
                              <th key={col}>{col}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {rows.length === 0 ? (
                            <tr>
                              <td colSpan={columns.length} className="empty-cell">
                                No rows in this table
                              </td>
                            </tr>
                          ) : (
                            rows.map((row, i) => (
                              <tr key={i}>
                                {columns.map((col) => (
                                  <td key={col}>
                                    {row[col] == null ? "—" : String(row[col])}
                                  </td>
                                ))}
                              </tr>
                            ))
                          )}
                        </tbody>
                      </table>
                    </div>

                    {totalPages > 1 && (
                      <div className="database-pagination">
                        <button
                          type="button"
                          disabled={currentPage <= 1}
                          onClick={() => selectedTable && loadTableData(selectedTable, offset - PAGE_SIZE)}
                        >
                          ◀ Prev
                        </button>
                        <span>
                          Page {currentPage} of {totalPages}
                        </span>
                        <button
                          type="button"
                          disabled={currentPage >= totalPages}
                          onClick={() => selectedTable && loadTableData(selectedTable, offset + PAGE_SIZE)}
                        >
                          Next ▶
                        </button>
                      </div>
                    )}
                  </>
                )}
              </>
            )}
          </main>
        </div>
      )}
    </div>
  );
}
