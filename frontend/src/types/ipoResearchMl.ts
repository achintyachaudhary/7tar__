export interface IpoResearchRun {
  id: number;
  algorithm: string;
  status: string;
  params: Record<string, unknown>;
  metrics: {
    sample_count?: number;
    positive_rate?: number;
    best_accuracy?: number;
    hit_rate?: number;
    summary_one_liner?: string;
  };
  insights: {
    target?: string;
    experiments?: IpoExperimentResult[];
    data_preparation?: Record<string, unknown>;
    narrative?: IpoResearchNarrative;
  };
  summary_text: string | null;
  sample_count: number | null;
  error_message: string | null;
  created_at: string | null;
  completed_at: string | null;
}

export interface IpoExampleRow {
  symbol: string;
  listing_date: string;
  gain_pct: number | null;
  market_1m_before_pct?: number;
  subscription_x?: number;
}

export interface IpoResearchNarrative {
  what_we_measured: string;
  bottom_line: string;
  takeaway_one_liner: string;
  hit_rate: number;
  sample_count: number;
  success_count: number;
  example_winners: IpoExampleRow[];
  example_losers: IpoExampleRow[];
  paragraphs: string[];
  caveats: string[];
}

export interface IpoExperimentResult {
  model: string;
  metrics: {
    test_accuracy: number;
    test_f1: number;
    cv_mean: number;
    cv_std: number;
    positive_rate: number;
  };
  top_features: { feature: string; importance: number }[];
  insights: string[];
}
