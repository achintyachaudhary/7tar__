import { useCallback, useEffect, useState } from "react";
import {
  fetchLmInspectOverview,
  fetchLmTable,
  fetchLmVectors,
  type LmInspectOverview,
  type LmTableData,
  type LmVectorsResponse,
} from "../api";

const VEC_PAGE = 20;
const TABLE_PAGE = 50;

function num(n: number | null | undefined): string {
  return n == null ? "—" : n.toLocaleString();
}

export default function StockAiDataPanel() {
  const [overview, setOverview] = useState<LmInspectOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [vectors, setVectors] = useState<LmVectorsResponse | null>(null);
  const [vecOffset, setVecOffset] = useState(0);
  const [expandedVec, setExpandedVec] = useState<string | null>(null);

  const [activeTable, setActiveTable] = useState<string | null>(null);
  const [tableData, setTableData] = useState<LmTableData | null>(null);
  const [tableOffset, setTableOffset] = useState(0);
  const [tableLoading, setTableLoading] = useState(false);

  useEffect(() => {
    fetchLmInspectOverview()
      .then(setOverview)
      .catch((e) =>
        setError(
          e instanceof Error
            ? `${e.message} — is the Stock AI service running? Start it with: uvicorn app.main:app --port 8010 (from lm/)`
            : String(e),
        ),
      )
      .finally(() => setLoading(false));
  }, []);

  const loadVectors = useCallback(async (offset: number) => {
    try {
      const data = await fetchLmVectors(offset, VEC_PAGE);
      setVectors(data);
      setVecOffset(data.offset);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    if (overview?.qdrant.available) void loadVectors(0);
  }, [overview, loadVectors]);

  const openTable = useCallback(async (table: string, offset: number) => {
    setActiveTable(table);
    setTableLoading(true);
    try {
      const data = await fetchLmTable(table, offset, TABLE_PAGE);
      setTableData(data);
      setTableOffset(data.offset);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setTableLoading(false);
    }
  }, []);

  if (loading) return <div className="status loading">Loading Stock AI data sources…</div>;
  if (error && !overview) return <div className="status error">{error}</div>;
  if (!overview) return null;

  const pg = overview.postgres;
  const qd = overview.qdrant;
  const vecPages = vectors ? Math.ceil(vectors.total / VEC_PAGE) : 0;
  const vecPage = Math.floor(vecOffset / VEC_PAGE) + 1;
  const tablePages = tableData ? Math.ceil(tableData.total / TABLE_PAGE) : 0;
  const tablePage = Math.floor(tableOffset / TABLE_PAGE) + 1;

  return (
    <div className="lm-data-panel">
      {/* ── Postgres ─────────────────────────────────────────────── */}
      <section className="lm-card">
        <div className="lm-card-head">
          <h2>🗃️ Postgres — used by Stock AI</h2>
          {pg.available && (
            <span className="lm-badge">{pg.source}</span>
          )}
        </div>

        {!pg.available ? (
          <div className="status error">{pg.reason ?? "database unavailable"}</div>
        ) : (
          <>
            <div className="lm-kv-grid">
              <div><span className="lm-kv-label">Active database</span><strong>{pg.active_database}</strong></div>
              <div><span className="lm-kv-label">Host</span>{pg.host}:{pg.port}</div>
              <div><span className="lm-kv-label">User</span>{pg.user ?? "—"}</div>
              <div><span className="lm-kv-label">Dialect</span>{pg.dialect}</div>
              <div className="lm-kv-wide">
                <span className="lm-kv-label">Connection</span>
                <code>{pg.dsn_masked}</code>
              </div>
            </div>
            <p className="lm-note">
              The Stock AI service reuses the main app's <strong>{pg.active_database}</strong>{" "}
              database (it does not use a separate one). Other databases on the same
              Postgres server are listed below.
            </p>

            {pg.server_databases && pg.server_databases.length > 0 && (
              <>
                <h3 className="lm-subhead">Databases on this server</h3>
                <div className="lm-db-chips">
                  {pg.server_databases.map((db) => (
                    <span
                      key={db.name}
                      className={`lm-db-chip${db.active ? " active" : ""}`}
                      title={db.active ? "Active — Stock AI is connected here" : ""}
                    >
                      {db.active ? "● " : ""}{db.name}
                      <span className="lm-db-size">{db.size}</span>
                    </span>
                  ))}
                </div>
              </>
            )}

            <h3 className="lm-subhead">Tables</h3>
            <table className="lm-tbl">
              <thead>
                <tr><th>Table</th><th>Rows</th><th>Managed by</th><th></th></tr>
              </thead>
              <tbody>
                {[...(pg.lm_tables ?? []), ...(pg.screener_tables ?? [])].map((t) => (
                  <tr key={t.name} className={activeTable === t.name ? "active" : ""}>
                    <td><code>{t.name}</code></td>
                    <td>{num(t.row_count)}</td>
                    <td><span className="lm-tag">{t.managed_by}</span></td>
                    <td>
                      <button type="button" className="lm-link-btn"
                        onClick={() => openTable(t.name, 0)}>
                        Browse →
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {activeTable && (
              <div className="lm-table-viewer">
                <div className="lm-table-viewer-head">
                  <h4><code>{activeTable}</code> · {num(tableData?.total)} rows</h4>
                  <button type="button" className="lm-link-btn" onClick={() => { setActiveTable(null); setTableData(null); }}>
                    ✕ close
                  </button>
                </div>
                {tableLoading ? (
                  <div className="status loading">Loading rows…</div>
                ) : tableData && (
                  <>
                    <div className="lm-table-scroll">
                      <table className="lm-tbl lm-tbl-data">
                        <thead>
                          <tr>{tableData.columns.map((c) => <th key={c}>{c}</th>)}</tr>
                        </thead>
                        <tbody>
                          {tableData.rows.length === 0 ? (
                            <tr><td colSpan={tableData.columns.length} className="lm-empty-cell">No rows</td></tr>
                          ) : tableData.rows.map((row, i) => (
                            <tr key={i}>
                              {tableData.columns.map((c) => (
                                <td key={c} title={row[c] == null ? "" : String(row[c])}>
                                  {row[c] == null ? "—" : String(row[c]).slice(0, 120)}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    {tablePages > 1 && (
                      <div className="lm-pager">
                        <button type="button" disabled={tablePage <= 1}
                          onClick={() => openTable(activeTable, tableOffset - TABLE_PAGE)}>◀ Prev</button>
                        <span>Page {tablePage} of {tablePages}</span>
                        <button type="button" disabled={tablePage >= tablePages}
                          onClick={() => openTable(activeTable, tableOffset + TABLE_PAGE)}>Next ▶</button>
                      </div>
                    )}
                  </>
                )}
              </div>
            )}
          </>
        )}
      </section>

      {/* ── Qdrant vectors ───────────────────────────────────────── */}
      <section className="lm-card">
        <div className="lm-card-head">
          <h2>🧬 Vector store — Qdrant embeddings</h2>
          {qd.available && <span className="lm-badge">{qd.collection}</span>}
        </div>

        {!qd.available ? (
          <div className="status error">{qd.reason ?? "Qdrant unavailable"} ({qd.url})</div>
        ) : (
          <>
            <div className="lm-kv-grid">
              <div><span className="lm-kv-label">Collection</span><strong>{qd.collection}</strong></div>
              <div><span className="lm-kv-label">Documents</span>{num(qd.points_count)}</div>
              <div><span className="lm-kv-label">Vector size</span>{num(qd.vector_size)} dims</div>
              <div><span className="lm-kv-label">Distance</span>{qd.distance}</div>
              <div><span className="lm-kv-label">Endpoint</span><code>{qd.url}</code></div>
            </div>

            <p className="lm-note">
              Each document below was turned into a {num(qd.vector_size)}-dimensional
              embedding. Click a row to preview the start of its actual vector.
            </p>

            {vectors && (
              <>
                <div className="lm-vec-list">
                  {vectors.points.length === 0 ? (
                    <div className="widget-empty">No embedded documents yet.</div>
                  ) : vectors.points.map((p) => (
                    <div key={p.id} className="lm-vec-item">
                      <button type="button" className="lm-vec-head"
                        onClick={() => setExpandedVec(expandedVec === p.id ? null : p.id)}>
                        <span className="lm-vec-ticker">{p.ticker ?? "—"}</span>
                        <span className="lm-vec-title">{p.title ?? p.text?.slice(0, 80)}</span>
                        <span className="lm-vec-source">{p.source}{p.date ? ` · ${p.date}` : ""}</span>
                        <span className="lm-vec-toggle">{expandedVec === p.id ? "▲" : "▼"}</span>
                      </button>
                      {expandedVec === p.id && (
                        <div className="lm-vec-body">
                          {p.text && <p className="lm-vec-text">{p.text}</p>}
                          <div className="lm-vec-embedding">
                            <span className="lm-kv-label">
                              Embedding ({num(p.vector_dim)} dims, first {p.vector_preview.length})
                            </span>
                            <code>[{p.vector_preview.join(", ")}{p.vector_dim && p.vector_dim > p.vector_preview.length ? ", …" : ""}]</code>
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
                {vecPages > 1 && (
                  <div className="lm-pager">
                    <button type="button" disabled={vecPage <= 1}
                      onClick={() => loadVectors(vecOffset - VEC_PAGE)}>◀ Prev</button>
                    <span>Page {vecPage} of {vecPages}</span>
                    <button type="button" disabled={vecPage >= vecPages}
                      onClick={() => loadVectors(vecOffset + VEC_PAGE)}>Next ▶</button>
                  </div>
                )}
              </>
            )}
          </>
        )}
      </section>
    </div>
  );
}
