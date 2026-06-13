import FinancialChart from "./FinancialChart";
import ShareholdingChart from "./ShareholdingChart";
import LazyDbChart from "./LazyDbChart";
import SymbolLink from "./SymbolLink";
import type { GoldenStockMatch } from "../types/golden";
import TimestampLabel from "./TimestampLabel";

interface GoldenStockRowProps {
  stock: GoldenStockMatch;
  lastScannedAt?: Date | null;
}

function fmtPct(v: number | null | undefined): string {
  if (v == null) return "—";
  const sign = v >= 0 ? "+" : "";
  return `${sign}${v.toFixed(1)}%`;
}

export default function GoldenStockRow({ stock, lastScannedAt }: GoldenStockRowProps) {
  const latestPromoter =
    stock.promoter_holding_pct ??
    stock.shareholding[0]?.promoter_holding_pct ??
    null;

  return (
    <article className="golden-stock-row">
      <div className="golden-stock-row-head">
        <div className="golden-stock-row-identity">
          <h3>
            <SymbolLink symbol={stock.symbol} />
          </h3>
          <span className="golden-stock-row-name">{stock.company_name}</span>
          {stock.industry && (
            <span className="golden-stock-row-industry">{stock.industry}</span>
          )}
        </div>
        <div className="golden-stock-row-price-block">
          <div className="golden-stock-row-price">₹{stock.price.toLocaleString()}</div>
          {stock.market_cap_cr != null && (
            <span className="golden-stock-row-mcap">
              MCap ₹{stock.market_cap_cr.toLocaleString()} Cr
            </span>
          )}
        </div>
      <div className="golden-stock-row-growth">
        {stock.rank_score != null && (
          <span className="golden-badge golden-badge-rank" title="Overall Rank Score">
            ⭐ Rank {stock.rank_score.toFixed(0)}/100
          </span>
        )}
        <span className="golden-badge golden-badge-price" title="Price YoY / QoQ">
          Price {fmtPct(stock.price_yoy_pct)} / {fmtPct(stock.price_qoq_pct)}
        </span>
          <span className="golden-badge golden-badge-rev" title="Revenue YoY">
            Rev {fmtPct(stock.revenue_growth_yoy_pct)}
          </span>
          <span className="golden-badge golden-badge-profit" title="Profit YoY">
            Profit {fmtPct(stock.profit_growth_yoy_pct)}
          </span>
          {latestPromoter != null && (
            <span className="golden-badge golden-badge-promoter" title="Promoter holding">
              Promoter {latestPromoter.toFixed(1)}%
            </span>
          )}
        </div>
      </div>

      <div className="golden-stock-row-panels">
        <div className="golden-panel golden-panel-chart">
          <div className="golden-panel-title-row">
            <h4 className="golden-panel-title">Weekly chart</h4>
          </div>
          <div className="golden-panel-chart-wrap">
            <LazyDbChart symbol={stock.symbol} interval="1wk" height={180} />
          </div>
        </div>

        <div className="golden-panel golden-panel-financial">
          <FinancialChart
            quarterly={stock.financials_quarterly}
            yearly={stock.financials_yearly}
            revenueGrowthYoy={stock.revenue_growth_yoy_pct}
            revenueCagr3y={null}
            profitGrowthYoy={stock.profit_growth_yoy_pct}
            profitCagr3y={null}
          />
        </div>

        <div className="golden-panel golden-panel-holding">
          {stock.shareholding.length > 0 ? (
            <ShareholdingChart periods={stock.shareholding} />
          ) : (
            <div className="insight-panel">
              <h3 className="panel-title">Shareholding Pattern</h3>
              <p className="panel-empty">
                {latestPromoter != null
                  ? `Promoter: ${latestPromoter.toFixed(2)}%`
                  : "Shareholding data not available."}
              </p>
            </div>
          )}
        </div>
      </div>
      {lastScannedAt && (
        <div className="widget-as-of">
          <TimestampLabel at={lastScannedAt} label="Scan" />
        </div>
      )}
    </article>
  );
}
