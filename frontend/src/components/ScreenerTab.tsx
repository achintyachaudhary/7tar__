import { useCallback, useEffect, useState } from "react";
import { fetchIndices, fetchScan } from "../api";
import type { IndexOption, ScanResponse } from "../types";
import StockTable from "./StockTable";
import { formatIST } from "../lib/formatTime";

const DEFAULT_INDEX = "nifty50";

export default function ScreenerTab() {
  const [indices, setIndices] = useState<IndexOption[]>([]);
  const [indexId, setIndexId] = useState(DEFAULT_INDEX);
  const [minScore, setMinScore] = useState(5);
  const [data, setData] = useState<ScanResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchIndices()
      .then((res) => setIndices(res.indices))
      .catch(() => {
        setIndices([
          { id: "nifty50", label: "Nifty 50", description: "", slow_scan: false },
          { id: "nifty100", label: "Nifty 100", description: "", slow_scan: false },
          { id: "nifty200", label: "Nifty 200", description: "", slow_scan: false },
          { id: "nifty500", label: "Nifty 500", description: "", slow_scan: false },
          { id: "nse_all", label: "All NSE (EQ)", description: "", slow_scan: true },
        ]);
      });
  }, []);

  const selectedIndex = indices.find((i) => i.id === indexId);
  const isSlowScan = selectedIndex?.slow_scan ?? indexId === "nse_all";

  const loadScan = useCallback(
    async (refresh = false) => {
      setLoading(true);
      setError(null);
      try {
        const result = await fetchScan(minScore, indexId, refresh);
        setData(result);
      } catch (err) {
        setData(null);
        setError(
          err instanceof Error
            ? err.message
            : "Failed to load scan. Is the backend running on port 8000?",
        );
      } finally {
        setLoading(false);
      }
    },
    [minScore, indexId],
  );

  useEffect(() => {
    loadScan(false);
  }, [loadScan]);

  const scannedAt = data?.scanned_at ?? null;

  const indexLabel =
    data?.index_label ?? selectedIndex?.label ?? "Nifty 50";

  return (
    <>
      <div className="tab-toolbar">
        <label>
          Index
          <select
            value={indexId}
            onChange={(e) => setIndexId(e.target.value)}
            disabled={loading}
          >
            {indices.length > 0 ? (
              indices.map((idx) => (
                <option key={idx.id} value={idx.id}>
                  {idx.label}
                </option>
              ))
            ) : (
              <>
                <option value="nifty50">Nifty 50</option>
                <option value="nifty100">Nifty 100</option>
                <option value="nifty200">Nifty 200</option>
                <option value="nifty500">Nifty 500</option>
                <option value="nse_all">All NSE (EQ)</option>
              </>
            )}
          </select>
        </label>
        <label>
          Min score
          <select
            value={minScore}
            onChange={(e) => setMinScore(Number(e.target.value))}
            disabled={loading}
          >
            <option value={4}>4+</option>
            <option value={5}>5+</option>
            <option value={6}>6+</option>
            <option value={7}>7+</option>
          </select>
        </label>
        <button
          type="button"
          disabled={loading}
          onClick={() => loadScan(true)}
        >
          Refresh scan
        </button>
      </div>

      {selectedIndex?.description && (
        <p className="meta index-desc">{selectedIndex.description}</p>
      )}

      {isSlowScan && (
        <p className="status warn-banner">
          Scanning all NSE equities can take 30–60+ minutes. Prefer Nifty indices
          for faster results.
        </p>
      )}

      {loading && (
        <div className="status loading">
          Scanning {indexLabel}…
          {isSlowScan
            ? " This may take a long time — keep this tab open."
            : " (may take a few minutes for larger indices)"}
        </div>
      )}

      {error && !loading && <div className="status error">{error}</div>}

      {!loading && !error && data && (
        <>
          <p className="meta">
            {data.index_label}: scanned {data.total_scanned} symbols ·{" "}
            {data.total_matched} matched (score ≥ {data.min_score}) · scanned{" "}
            {formatIST(scannedAt)}
          </p>
          {data.results.length === 0 ? (
            <div className="status">
              No stocks matched score ≥ {data.min_score}. Try lowering the
              threshold or another index.
            </div>
          ) : (
            <StockTable rows={data.results} />
          )}
        </>
      )}
    </>
  );
}
