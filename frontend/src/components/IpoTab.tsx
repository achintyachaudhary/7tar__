import { useCallback, useEffect, useState } from "react";
import { fetchIpos } from "../api";
import type { IpoTrackResponse } from "../types";
import IpoTable from "./IpoTable";
import { formatIST } from "../lib/formatTime";

export default function IpoTab() {
  const [months, setMonths] = useState<1 | 2 | 6>(6);
  const [data, setData] = useState<IpoTrackResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadIpos = useCallback(async (refresh = false) => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchIpos(months, refresh);
      setData(result);
    } catch (err) {
      setData(null);
      setError(
        err instanceof Error
          ? err.message
          : "Failed to load IPO data. Is the backend running?",
      );
    } finally {
      setLoading(false);
    }
  }, [months]);

  useEffect(() => {
    loadIpos(false);
  }, [loadIpos]);

  const scannedAt = data?.scanned_at ?? null;

  return (
    <>
      <p className="meta index-desc">
        Recent NSE IPOs with listing-day and post-listing performance (issue
        price vs listing close vs current price).
      </p>

      <div className="tab-toolbar">
        <label>
          Period
          <select
            value={months}
            onChange={(e) => setMonths(Number(e.target.value) as 1 | 2 | 6)}
            disabled={loading}
          >
            <option value={1}>Last 1 month</option>
            <option value={2}>Last 2 months</option>
            <option value={6}>Last 6 months</option>
          </select>
        </label>
        <button
          type="button"
          disabled={loading}
          onClick={() => loadIpos(true)}
        >
          Refresh IPOs
        </button>
      </div>

      {loading && (
        <div className="status loading">
          Loading IPO listings and market prices…
        </div>
      )}

      {error && !loading && <div className="status error">{error}</div>}

      {!loading && !error && data && (
        <>
          <p className="meta">
            {data.total_listed} IPOs listed in last {data.months} month
            {data.months > 1 ? "s" : ""} · {data.with_market_data} with price
            data · scanned {formatIST(scannedAt)}
          </p>
          {data.results.length === 0 ? (
            <div className="status">No IPO listings found for this period.</div>
          ) : (
            <IpoTable rows={data.results} />
          )}
        </>
      )}
    </>
  );
}
