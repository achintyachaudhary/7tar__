import type { OhlcBar } from "./chart";
import type { FinancialPeriod, ShareholdingPeriod } from "./insights";

export interface WeeklyStockMatch {
  symbol: string;
  company_name: string;
  industry: string | null;
  market_cap_cr: number | null;
  market_cap_category: string | null;
  price: number;
  /** Weekly YoY price change */
  price_yoy_pct: number;
  /** Weekly 4-week price change (stored as price_qoq_pct for shared shape) */
  price_qoq_pct: number;
  revenue_growth_yoy_pct: number | null;
  profit_growth_yoy_pct: number | null;
  promoter_holding_pct: number | null;
  fii_holding_pct: number | null;
  dii_holding_pct: number | null;
  retail_holding_pct: number | null;
  mutual_fund_holding_pct: number | null;
  promoter_increasing: boolean | null;
  fii_increasing: boolean | null;
  dii_increasing: boolean | null;
  mutual_fund_increasing: boolean | null;
  rank_score?: number;
  financials_quarterly: FinancialPeriod[];
  financials_yearly: FinancialPeriod[];
  shareholding: ShareholdingPeriod[];
  weekly_bars?: OhlcBar[];
}
