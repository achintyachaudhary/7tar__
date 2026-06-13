export type StockListTag = "favorite" | "fishy" | "blacklist";

export interface EnrichedStockListRow {
  symbol: string;
  company_name: string;
  industry: string | null;
  market_cap_cr: number | null;
  ltp: number | null;
  change_day_pct: number | null;
  change_day_pct_live?: boolean;
  change_7d_pct: number | null;
  tags: StockListTag[];
}

export type StockListFilter = "all" | StockListTag;
