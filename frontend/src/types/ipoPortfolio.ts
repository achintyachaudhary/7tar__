export interface IpoScenarioTrade {
  gain_pct: number;
  final_value_inr: number;
  profit_inr: number;
  roi_pct: number;
}

export interface IpoPortfolioScenarioSummary {
  id: string;
  label: string;
  entry_label: string;
  exit_label: string;
  ipos_included: number;
  total_invested_inr: number;
  total_final_value_inr: number;
  total_profit_inr: number;
  portfolio_roi_pct: number | null;
  winners: number;
  losers: number;
  avg_gain_pct: number | null;
  best_ipo: { symbol: string; profit_inr: number; gain_pct: number } | null;
  worst_ipo: { symbol: string; profit_inr: number; gain_pct: number } | null;
}

export interface IpoPortfolioPerIpo {
  symbol: string;
  company_name?: string;
  listing_date: string;
  issue_price: number | null;
  listing_open: number | null;
  listing_close: number | null;
  current_price: number | null;
  scenarios: Record<string, IpoScenarioTrade | null>;
}

export interface IpoPortfolioSimulation {
  investment_per_ipo_inr: number;
  months: number | null;
  ipo_count: number;
  disclaimer: string;
  scenarios: IpoPortfolioScenarioSummary[];
  per_ipo: IpoPortfolioPerIpo[];
}
