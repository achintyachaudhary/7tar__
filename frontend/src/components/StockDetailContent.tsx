import { useEffect, useState } from "react";
import { fetchStockInsights, refreshStockData } from "../api";
import type { StockInsightsResponse } from "../types";
import FinancialChart from "./FinancialChart";
import ShareholdingChart from "./ShareholdingChart";
import VolumePanel from "./VolumePanel";
import IpoLlmResearchPanel from "./IpoLlmResearchPanel";
import StockChartPanel from "./StockChartPanel";
import { formatIST } from "../lib/formatTime";

function fmtCapCr(v: number | null): string {
  if (v == null) return "—";
  if (v >= 100_000) return `₹${(v / 100_000).toFixed(2)} L Cr`;
  if (v >= 1000) return `₹${(v / 1000).toFixed(1)}k Cr`;
  return `₹${v.toFixed(0)} Cr`;
}

function fmtTs(ts: string | null): string {
  if (!ts) return "never";
  const formatted = formatIST(ts);
  return formatted === "—" ? "never" : formatted;
}

interface StockDetailContentProps {
  symbol: string;
  yfSymbol?: string | null;
  companyName?: string | null;
  showIpoResearch?: boolean;
}

export default function StockDetailContent({
  symbol,
  yfSymbol,
  companyName,
  showIpoResearch = false,
}: StockDetailContentProps) {
  const [data, setData] = useState<StockInsightsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchSymbol = yfSymbol || symbol;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setData(null);

    fetchStockInsights(fetchSymbol)
      .then((res) => { if (!cancelled) setData(res); })
      .catch((err) => { if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load"); })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [fetchSymbol]);

  async function handleRefresh() {
    setRefreshing(true);
    setError(null);
    try {
      const res = await refreshStockData(fetchSymbol);
      setData(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Refresh failed");
    } finally {
      setRefreshing(false);
    }
  }

  if (loading) {
    return <p className="panel-loading">Loading company details…</p>;
  }

  if (error && !data) {
    return <p className="panel-error">{error}</p>;
  }

  if (!data) return null;

  return (
    <>
      {/* Data freshness + Refresh button */}
      <div className="refresh-bar">
        <span>
          Profile: <strong>{fmtTs(data.last_profile_updated)}</strong>
        </span>
        <span>·</span>
        <span>
          Holdings: <strong>{fmtTs(data.last_holdings_updated)}</strong>
        </span>
        <span>·</span>
        <span>
          Financials: <strong>{fmtTs(data.last_financials_updated)}</strong>
        </span>
        <button
          type="button"
          className="refresh-btn"
          disabled={refreshing}
          onClick={handleRefresh}
        >
          {refreshing ? "Refreshing…" : "↻ Refresh Data"}
        </button>
        {error && <span style={{ color: "var(--red)" }}>{error}</span>}
      </div>

      {showIpoResearch && (
        <IpoLlmResearchPanel symbol={symbol} companyName={companyName} />
      )}

      <StockChartPanel symbol={symbol} yfSymbol={yfSymbol} />

      <VolumePanel symbol={fetchSymbol} />

      <div className="detail-meta">
        <div className="detail-meta-row">
          {data.market_cap_category && (
            <span className={`meta-badge cap-${data.market_cap_category.split(" ")[0].toLowerCase()}`}>
              {data.market_cap_category}
            </span>
          )}
          {data.sector && (
            <span className="meta-badge sector">{data.sector}</span>
          )}
          {data.industry && (
            <span className="meta-badge industry">{data.industry}</span>
          )}
          {data.overall_score != null && (
            <span
              className={`overall-score ${
                data.overall_score >= 6.5
                  ? "score-green"
                  : data.overall_score >= 4
                  ? "score-amber"
                  : "score-red"
              }`}
              style={{ width: "auto", borderRadius: "6px", padding: "0.2rem 0.5rem" }}
              title="Overall score (0–10)"
            >
              ★ {data.overall_score}/10
            </span>
          )}
        </div>
        {data.market_cap_cr != null && (
          <p className="meta-cap-value">
            Market cap: {fmtCapCr(data.market_cap_cr)}
          </p>
        )}
      </div>

      <div className="detail-grid">
        <ShareholdingChart periods={data.shareholding} />
        <FinancialChart
          quarterly={data.financials_quarterly}
          yearly={data.financials_yearly}
          revenueGrowthYoy={data.revenue_growth_yoy_pct}
          revenueCagr3y={data.revenue_cagr_3y_pct}
          profitGrowthYoy={data.profit_growth_yoy_pct}
          profitCagr3y={data.profit_cagr_3y_pct}
        />
      </div>
    </>
  );
}
