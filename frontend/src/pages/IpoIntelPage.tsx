import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchIpoIntel, fetchIpoIntelStatus, refreshIpoIntel } from "../api";
import SortableTh from "../components/SortableTh";
import { useTableSort } from "../hooks/useTableSort";
import { formatIST } from "../lib/formatTime";
import type { IpoIntelJobStatus, IpoIntelRow } from "../types/ipoIntel";

const STATUS_ORDER: Record<string, number> = { open: 0, upcoming: 1, closed: 2, listed: 3 };
const STATUS_FILTERS = ["all", "open", "upcoming", "closed", "listed"] as const;
type StatusFilter = (typeof STATUS_FILTERS)[number];

const POLL_MS = 3_000;

function fmtX(v: number | null): string {
  return v == null ? "—" : `${v.toLocaleString("en-IN", { maximumFractionDigits: 2 })}×`;
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(`${iso}T00:00:00`);
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}

function sortValue(row: IpoIntelRow, key: string): string | number | null {
  switch (key) {
    case "name":
      return row.display_name;
    case "status":
      return row.status ? STATUS_ORDER[row.status] ?? 9 : 9;
    case "gmp_pct":
      return row.gmp_pct;
    case "rating":
      return row.rating;
    case "sub_total":
      return row.sub_total;
    case "sub_retail":
      return row.sub_retail;
    case "sub_qib":
      return row.sub_qib;
    case "open_date":
      return row.open_date;
    case "listing_date":
      return row.listing_date;
    default:
      return null;
  }
}

export default function IpoIntelPage() {
  const [rows, setRows] = useState<IpoIntelRow[]>([]);
  const [job, setJob] = useState<IpoIntelJobStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const pollRef = useRef<number | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await fetchIpoIntel();
      setRows(res.rows);
      setJob(res.job);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load IPO intel");
    } finally {
      setLoading(false);
    }
  }, []);

  const stopPolling = useCallback(() => {
    if (pollRef.current != null) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const pollWhileRunning = useCallback(() => {
    stopPolling();
    pollRef.current = window.setInterval(async () => {
      try {
        const status = await fetchIpoIntelStatus();
        setJob(status);
        if (!status.running) {
          stopPolling();
          await load();
        }
      } catch {
        stopPolling();
      }
    }, POLL_MS);
  }, [load, stopPolling]);

  useEffect(() => {
    void load();
    return stopPolling;
  }, [load, stopPolling]);

  // Attach to an in-flight scrape (e.g. scheduled run) on mount.
  useEffect(() => {
    if (job?.running && pollRef.current == null) pollWhileRunning();
  }, [job?.running, pollWhileRunning]);

  const handleScrape = useCallback(async () => {
    setError(null);
    try {
      const res = await refreshIpoIntel();
      setJob(res);
      pollWhileRunning();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start scrape");
    }
  }, [pollWhileRunning]);

  const filtered = useMemo(
    () => (statusFilter === "all" ? rows : rows.filter((r) => r.status === statusFilter)),
    [rows, statusFilter],
  );

  const getValue = useCallback((row: IpoIntelRow, key: string) => sortValue(row, key), []);
  const { sortedRows, sortKey, sortDir, toggleSort } = useTableSort(
    filtered,
    "status",
    "asc",
    getValue,
  );

  const lastFetch = rows[0]?.fetched_at ?? job?.summary?.fetched_at ?? null;
  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const r of rows) c[r.status ?? "tba"] = (c[r.status ?? "tba"] ?? 0) + 1;
    return c;
  }, [rows]);

  return (
    <div className="page-container ipo-intel-page">
      <div className="page-header ipo-intel-header">
        <div>
          <h1>IPO Intel — GMP &amp; Subscriptions</h1>
          <p className="page-subtitle">
            Grey-market premium and live bidding data scraped via headless browser from
            InvestorGain and Chittorgarh. Runs daily at the scheduled time (see Schedule page)
            or on demand below.
          </p>
        </div>
        <button
          type="button"
          className="btn-primary ipo-intel-scrape-btn"
          disabled={Boolean(job?.running)}
          onClick={() => void handleScrape()}
        >
          {job?.running ? "Scraping…" : "Scrape now"}
        </button>
      </div>

      <div className="ipo-intel-meta">
        {job?.running && (
          <span className="ipo-intel-running">
            <span className="market-session-dot" aria-hidden /> Headless browser running — this
            takes ~20–30s
          </span>
        )}
        {!job?.running && lastFetch && (
          <span>
            Last scraped <strong>{formatIST(lastFetch)}</strong>
          </span>
        )}
        {job?.error && <span className="negative">Last run failed: {job.error}</span>}
        {job?.summary && !job.running && (
          <span className="ipo-intel-summary">
            {job.summary.gmp_rows} GMP rows · {job.summary.subscription_rows} subscription rows
            {job.summary.verified_rows != null && (
              <> · {job.summary.verified_rows} verified via Upstox</>
            )}
          </span>
        )}
      </div>

      <div className="ipo-intel-filters">
        {STATUS_FILTERS.map((f) => (
          <button
            key={f}
            type="button"
            className={`toolbar-btn ipo-intel-filter${statusFilter === f ? " active" : ""}`}
            onClick={() => setStatusFilter(f)}
          >
            {f === "all" ? `All (${rows.length})` : `${f} (${counts[f] ?? 0})`}
          </button>
        ))}
      </div>

      {error && <div className="status error">{error}</div>}
      {loading && <div className="status loading">Loading IPO intel…</div>}

      {!loading && sortedRows.length === 0 && !error && (
        <div className="status">
          No IPO data yet — hit <strong>Scrape now</strong> to fetch the latest GMP and
          subscription numbers.
        </div>
      )}

      {sortedRows.length > 0 && (
        <div className="table-wrap">
          <table className="ipo-intel-table">
            <thead>
              <tr>
                <SortableTh label="IPO" sortKey="name" activeKey={sortKey} direction={sortDir} onSort={toggleSort} />
                <SortableTh label="Status" sortKey="status" activeKey={sortKey} direction={sortDir} onSort={toggleSort} />
                <th>Price band</th>
                <SortableTh label="GMP" sortKey="gmp_pct" activeKey={sortKey} direction={sortDir} onSort={toggleSort} />
                <SortableTh label="Rating" sortKey="rating" activeKey={sortKey} direction={sortDir} onSort={toggleSort} />
                <SortableTh label="QIB" sortKey="sub_qib" activeKey={sortKey} direction={sortDir} onSort={toggleSort} />
                <th>NII</th>
                <SortableTh label="Retail" sortKey="sub_retail" activeKey={sortKey} direction={sortDir} onSort={toggleSort} />
                <SortableTh label="Total subs" sortKey="sub_total" activeKey={sortKey} direction={sortDir} onSort={toggleSort} />
                <SortableTh label="Open – Close" sortKey="open_date" activeKey={sortKey} direction={sortDir} onSort={toggleSort} />
                <SortableTh label="Listing" sortKey="listing_date" activeKey={sortKey} direction={sortDir} onSort={toggleSort} />
                <th>Updated</th>
              </tr>
            </thead>
            <tbody>
              {sortedRows.map((r) => (
                <tr key={r.name_key}>
                  <td className="ipo-intel-name">
                    <span className="ipo-intel-name-line">
                      {r.display_name}
                      {r.upstox_verified && (
                        <span
                          className="ipo-intel-verified"
                          title={`Verified against the Upstox IPO catalog${
                            r.upstox_symbol ? ` — symbol ${r.upstox_symbol}` : ""
                          }${r.isin ? ` · ISIN ${r.isin}` : ""}`}
                        >
                          ✓ Upstox
                        </span>
                      )}
                    </span>
                    <span className="ipo-intel-sub">
                      {r.ipo_type === "sme" ? "SME" : "Mainboard"}
                      {r.upstox_symbol ? ` · ${r.upstox_symbol}` : ""}
                      {r.ipo_size ? ` · ${r.ipo_size}` : ""}
                      {r.industry ? ` · ${r.industry}` : ""}
                    </span>
                  </td>
                  <td>
                    <span className={`ipo-intel-status ipo-intel-status-${r.status ?? "tba"}`}>
                      {r.status ?? "TBA"}
                    </span>
                  </td>
                  <td>{r.price_band ? `₹${r.price_band}` : "—"}</td>
                  <td className={r.gmp_pct != null ? (r.gmp_pct >= 0 ? "positive" : "negative") : ""}>
                    {r.gmp != null ? `₹${r.gmp}` : "—"}
                    {r.gmp_pct != null && (
                      <span className="ipo-intel-sub">
                        {r.gmp_pct >= 0 ? "+" : ""}
                        {r.gmp_pct}%
                      </span>
                    )}
                  </td>
                  <td title={r.rating != null ? `${r.rating}/5 fire rating` : undefined}>
                    {r.rating != null ? "🔥".repeat(r.rating) : "—"}
                  </td>
                  <td>{fmtX(r.sub_qib)}</td>
                  <td>{fmtX(r.sub_nii)}</td>
                  <td>{fmtX(r.sub_retail)}</td>
                  <td className={r.sub_total != null && r.sub_total >= 1 ? "positive" : ""}>
                    {fmtX(r.sub_total)}
                    {r.sub_applications && (
                      <span className="ipo-intel-sub">{r.sub_applications} applications</span>
                    )}
                  </td>
                  <td className="ipo-intel-dates">
                    {fmtDate(r.open_date)} – {fmtDate(r.close_date)}
                  </td>
                  <td>{fmtDate(r.listing_date)}</td>
                  <td className="ipo-intel-updated">
                    {r.gmp_updated_at && <span className="ipo-intel-sub">GMP {r.gmp_updated_at}</span>}
                    {r.sub_as_of && <span className="ipo-intel-sub">Subs {r.sub_as_of}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
