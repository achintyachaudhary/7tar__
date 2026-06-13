export interface CategorySubscription {
  shares_offered: number | null;
  times_subscribed: number | null;
}

export interface CategoryBreakdown {
  qualified_institutional_buyers_qib?: CategorySubscription | null;
  non_institutional_investors_nii?: CategorySubscription | null;
  retail_individual_investors_rii?: CategorySubscription | null;
  employee_reservation?: CategorySubscription | null;
}

export interface IpoSubscriptionResearch {
  company_name: string;
  ticker_symbol: string;
  bidding_period: { open_date: string; close_date: string };
  pricing: {
    price_band_inr: { floor: number | null; cap: number | null };
    final_issue_price_inr: number | null;
  };
  issue_details: {
    total_issue_size_crores_inr: number | null;
    total_shares_offered: number | null;
    total_shares_bid_for: number | null;
    issue_type: string;
  };
  subscription_summary: {
    overall_times_subscribed: number | null;
    category_breakdown: CategoryBreakdown;
  };
}

export type IpoLlmFetchStatus = "pending" | "fetching" | "fetched" | "failed";

export interface IpoLlmStatusItem {
  symbol: string;
  status: "pending" | "fetched" | "failed";
  fetched_at: string | null;
  error_message: string | null;
  overall_times_subscribed: number | null;
}

export interface IpoLlmStatusResponse {
  statuses: IpoLlmStatusItem[];
}

export interface IpoBatchFetchResponse {
  results: { symbol: string; status: string; error: string | null }[];
  fetched_count: number;
  failed_count: number;
  skipped_count: number;
}

export interface IpoLlmResearchResponse {
  symbol: string;
  provider: string;
  fetched_at: string;
  data: IpoSubscriptionResearch;
  from_cache: boolean;
  status?: string;
}
