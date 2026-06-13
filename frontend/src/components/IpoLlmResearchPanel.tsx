import { useCallback, useEffect, useState } from "react";
import {
  fetchIpoLlmResearch,
  generateIpoLlmResearch,
} from "../api";
import type {
  CategorySubscription,
  IpoLlmResearchResponse,
} from "../types/ipoResearch";
import { formatIST } from "../lib/formatTime";

function fmtNum(v: number | null | undefined, digits = 2): string {
  if (v == null) return "—";
  return v.toLocaleString("en-IN", { maximumFractionDigits: digits });
}

function fmtInt(v: number | null | undefined): string {
  if (v == null) return "—";
  return v.toLocaleString("en-IN");
}

interface IpoLlmResearchPanelProps {
  symbol: string;
  companyName?: string | null;
}

export default function IpoLlmResearchPanel({
  symbol,
  companyName,
}: IpoLlmResearchPanelProps) {
  const [data, setData] = useState<IpoLlmResearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadCached = useCallback(async () => {
    try {
      const res = await fetchIpoLlmResearch(symbol);
      setData(res);
      setError(null);
    } catch {
      setData(null);
    }
  }, [symbol]);

  useEffect(() => {
    setData(null);
    setError(null);
    void loadCached();
  }, [loadCached, symbol]);

  async function handleGenerate(refresh = false) {
    setLoading(true);
    setError(null);
    try {
      const res = await generateIpoLlmResearch(symbol, {
        companyName: companyName ?? undefined,
        refresh,
      });
      setData(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "IPO research failed");
    } finally {
      setLoading(false);
    }
  }

  const d = data?.data;
  const cats = d?.subscription_summary.category_breakdown;

  const categoryRows: { key: string; label: string; sub?: CategorySubscription | null }[] = [
    { key: "qib", label: "QIB", sub: cats?.qualified_institutional_buyers_qib },
    { key: "nii", label: "NII", sub: cats?.non_institutional_investors_nii },
    { key: "rii", label: "Retail (RII)", sub: cats?.retail_individual_investors_rii },
    { key: "emp", label: "Employee", sub: cats?.employee_reservation },
  ];

  return (
    <section className="ipo-research-panel">
      <div className="ipo-research-header">
        <h3>IPO subscription (LLM)</h3>
        <div className="ipo-research-actions">
          <button
            type="button"
            className="refresh-btn"
            disabled={loading}
            onClick={() => void handleGenerate(false)}
          >
            {loading ? "Fetching…" : data ? "↻ Regenerate" : "✦ Fetch IPO data"}
          </button>
          {data && (
            <span className="ipo-research-meta">
              {data.from_cache ? "cached" : "fresh"} · {data.provider} ·{" "}
              {formatIST(data.fetched_at)}
            </span>
          )}
        </div>
      </div>

      {error && <p className="panel-error">{error}</p>}

      {!d && !loading && !error && (
        <p className="ipo-research-hint">
          No stored IPO research yet. Click Fetch to call Gemini and save subscription
          breakdown to the database.
        </p>
      )}

      {d && (
        <div className="ipo-research-body">
          <p className="ipo-research-company">
            <strong>{d.company_name}</strong> ({d.ticker_symbol})
          </p>
          <div className="ipo-research-grid">
            <div>
              <span className="ipo-label">Bidding</span>
              <span>
                {d.bidding_period.open_date || "—"} → {d.bidding_period.close_date || "—"}
              </span>
            </div>
            <div>
              <span className="ipo-label">Price band</span>
              <span>
                ₹{fmtNum(d.pricing.price_band_inr.floor)} – ₹
                {fmtNum(d.pricing.price_band_inr.cap)}
              </span>
            </div>
            <div>
              <span className="ipo-label">Issue price</span>
              <span>₹{fmtNum(d.pricing.final_issue_price_inr)}</span>
            </div>
            <div>
              <span className="ipo-label">Issue type</span>
              <span>{d.issue_details.issue_type || "—"}</span>
            </div>
            <div>
              <span className="ipo-label">Issue size</span>
              <span>
                {d.issue_details.total_issue_size_crores_inr != null
                  ? `₹${fmtNum(d.issue_details.total_issue_size_crores_inr)} Cr`
                  : "—"}
              </span>
            </div>
            <div>
              <span className="ipo-label">Overall subscribed</span>
              <span className="ipo-highlight">
                {fmtNum(d.subscription_summary.overall_times_subscribed)}×
              </span>
            </div>
          </div>

          <table className="ipo-sub-table">
            <thead>
              <tr>
                <th>Category</th>
                <th>Shares offered</th>
                <th>Times subscribed</th>
              </tr>
            </thead>
            <tbody>
              {categoryRows.map(({ key, label, sub }) => (
                <tr key={key}>
                  <td>{label}</td>
                  <td>{fmtInt(sub?.shares_offered)}</td>
                  <td>{fmtNum(sub?.times_subscribed)}×</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
