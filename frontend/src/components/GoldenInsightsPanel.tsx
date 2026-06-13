import { useMemo } from "react";
import type { GoldenStockMatch } from "../types/golden";

interface GoldenInsightsPanelProps {
  matches: GoldenStockMatch[];
  onIndustryFilter: (industry: string) => void;
}

export default function GoldenInsightsPanel({
  matches,
  onIndustryFilter,
}: GoldenInsightsPanelProps) {
  const insights = useMemo(() => {
    if (matches.length === 0) {
      return {
        totalStocks: 0,
        avgRankScore: 0,
        topIndustries: [],
        avgPriceGrowth: 0,
        avgRevenueGrowth: 0,
        avgProfitGrowth: 0,
        highPromoter: 0,
        lowRetail: 0,
      };
    }

    // Industry breakdown
    const industryMap = new Map<string, number>();
    let totalRank = 0;
    let totalPriceYoy = 0;
    let totalRevYoy = 0;
    let totalProfitYoy = 0;
    let countPriceYoy = 0;
    let countRevYoy = 0;
    let countProfitYoy = 0;
    let highPromoterCount = 0;
    let lowRetailCount = 0;

    for (const stock of matches) {
      if (stock.industry) {
        industryMap.set(stock.industry, (industryMap.get(stock.industry) || 0) + 1);
      }

      totalRank += stock.rank_score || 0;

      if (stock.price_yoy_pct != null) {
        totalPriceYoy += stock.price_yoy_pct;
        countPriceYoy++;
      }

      if (stock.revenue_growth_yoy_pct != null) {
        totalRevYoy += stock.revenue_growth_yoy_pct;
        countRevYoy++;
      }

      if (stock.profit_growth_yoy_pct != null) {
        totalProfitYoy += stock.profit_growth_yoy_pct;
        countProfitYoy++;
      }

      if (stock.promoter_holding_pct != null && stock.promoter_holding_pct >= 50) {
        highPromoterCount++;
      }

      if (stock.shareholding.length > 0) {
        const retail = stock.shareholding[0].retail_and_others_pct;
        if (retail != null && retail < 30) {
          lowRetailCount++;
        }
      }
    }

    const topIndustries = Array.from(industryMap.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
      .map(([industry, count]) => ({ industry, count }));

    return {
      totalStocks: matches.length,
      avgRankScore: totalRank / matches.length,
      topIndustries,
      avgPriceGrowth: countPriceYoy > 0 ? totalPriceYoy / countPriceYoy : 0,
      avgRevenueGrowth: countRevYoy > 0 ? totalRevYoy / countRevYoy : 0,
      avgProfitGrowth: countProfitYoy > 0 ? totalProfitYoy / countProfitYoy : 0,
      highPromoter: highPromoterCount,
      lowRetail: lowRetailCount,
    };
  }, [matches]);

  if (matches.length === 0) {
    return null;
  }

  return (
    <div className="golden-insights">
      <h3 className="golden-insights-title">📊 Portfolio Insights</h3>
      <div className="golden-insights-grid">
        <div className="golden-insight-card">
          <span className="golden-insight-label">Total Stocks</span>
          <span className="golden-insight-value">{insights.totalStocks}</span>
        </div>

        <div className="golden-insight-card">
          <span className="golden-insight-label">Avg Rank Score</span>
          <span className="golden-insight-value rank-score">
            {insights.avgRankScore.toFixed(1)}/100
          </span>
        </div>

        <div className="golden-insight-card">
          <span className="golden-insight-label">Avg Price Growth (YoY)</span>
          <span className="golden-insight-value positive">
            +{insights.avgPriceGrowth.toFixed(1)}%
          </span>
        </div>

        <div className="golden-insight-card">
          <span className="golden-insight-label">Avg Revenue Growth</span>
          <span className="golden-insight-value positive">
            +{insights.avgRevenueGrowth.toFixed(1)}%
          </span>
        </div>

        <div className="golden-insight-card">
          <span className="golden-insight-label">Avg Profit Growth</span>
          <span className="golden-insight-value positive">
            +{insights.avgProfitGrowth.toFixed(1)}%
          </span>
        </div>

        <div className="golden-insight-card">
          <span className="golden-insight-label">High Promoter (≥50%)</span>
          <span className="golden-insight-value">
            {insights.highPromoter} ({((insights.highPromoter / insights.totalStocks) * 100).toFixed(0)}%)
          </span>
        </div>

        <div className="golden-insight-card">
          <span className="golden-insight-label">Low Retail (&lt;30%)</span>
          <span className="golden-insight-value">
            {insights.lowRetail} ({((insights.lowRetail / insights.totalStocks) * 100).toFixed(0)}%)
          </span>
        </div>
      </div>

      {insights.topIndustries.length > 0 && (
        <div className="golden-insights-industries">
          <h4>Top Industries</h4>
          <div className="golden-industry-chips">
            {insights.topIndustries.map(({ industry, count }) => (
              <button
                key={industry}
                type="button"
                className="golden-industry-chip"
                onClick={() => onIndustryFilter(industry)}
                title={`Filter by ${industry}`}
              >
                {industry} <span className="chip-count">({count})</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
