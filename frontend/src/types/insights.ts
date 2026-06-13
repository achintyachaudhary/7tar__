export interface ShareholdingPeriod {
  as_of: string;
  label: string;
  promoter_holding_pct: number | null;
  fii_holding_pct: number | null;
  dii_holding_pct: number | null;
  public_holding_pct: number | null;
  retail_and_others_pct: number | null;
  mutual_fund_holding_pct: number | null;
}

export interface FinancialPeriod {
  period: string;
  label: string;
  revenue_cr: number | null;
  profit_cr: number | null;
}

export interface StockInsightsResponse {
  symbol: string;
  company_name: string;
  sector: string | null;
  industry: string | null;
  market_cap_cr: number | null;
  market_cap_category: string | null;
  overall_score: number | null;
  shareholding: ShareholdingPeriod[];
  financials_quarterly: FinancialPeriod[];
  financials_yearly: FinancialPeriod[];
  revenue_growth_yoy_pct: number | null;
  revenue_cagr_3y_pct: number | null;
  profit_growth_yoy_pct: number | null;
  profit_cagr_3y_pct: number | null;
  last_profile_updated: string | null;
  last_holdings_updated: string | null;
  last_financials_updated: string | null;
}

export interface SelectedStock {
  symbol: string;
  yfSymbol?: string | null;
  label?: string;
}
