export interface IpoIntelRow {
  name_key: string;
  display_name: string;
  ipo_type: "mainboard" | "sme" | null;
  status: "upcoming" | "open" | "closed" | "listed" | null;
  price_band: string | null;
  ipo_size: string | null;
  lot_size: string | null;
  gmp: number | null;
  gmp_pct: number | null;
  rating: number | null;
  open_date: string | null;
  close_date: string | null;
  listing_date: string | null;
  sub_qib: number | null;
  sub_nii: number | null;
  sub_retail: number | null;
  sub_total: number | null;
  sub_applications: string | null;
  sub_as_of: string | null;
  gmp_updated_at: string | null;
  sources: string | null;
  upstox_verified: boolean;
  upstox_symbol: string | null;
  isin: string | null;
  industry: string | null;
  upstox_id: string | null;
  fetched_at: string | null;
}

export interface IpoIntelJobStatus {
  running: boolean;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  summary: {
    gmp_rows: number;
    subscription_rows: number;
    merged_rows: number;
    verified_rows?: number;
    pruned_rows: number;
    fetched_at: string;
  } | null;
}

export interface IpoIntelResponse {
  rows: IpoIntelRow[];
  count: number;
  job: IpoIntelJobStatus;
}
