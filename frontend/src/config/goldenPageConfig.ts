import type { FilterSectionDef } from "../components/GenericFiltersPanel";
import type { SortOption } from "../lib/filterSort";
import type { GoldenStockMatch } from "../types/golden";
import type { FilterValues } from "../lib/filterSort";

export const GOLDEN_SORT_OPTIONS: SortOption<GoldenStockMatch>[] = [
  { id: "rank", label: "Rank", getValue: (m) => m.rank_score ?? 0, defaultDirection: "desc" },
  { id: "price", label: "Price", getValue: (m) => m.price },
  { id: "priceGrowth", label: "Growth", getValue: (m) => m.price_yoy_pct, defaultDirection: "desc" },
  {
    id: "revenueGrowth",
    label: "Revenue",
    getValue: (m) => m.revenue_growth_yoy_pct ?? 0,
    defaultDirection: "desc",
  },
  {
    id: "profitGrowth",
    label: "Profit",
    getValue: (m) => m.profit_growth_yoy_pct ?? 0,
    defaultDirection: "desc",
  },
  {
    id: "promoter",
    label: "Promoter",
    getValue: (m) => m.promoter_holding_pct ?? 0,
    defaultDirection: "desc",
  },
  { id: "fii", label: "FII", getValue: (m) => m.fii_holding_pct ?? 0, defaultDirection: "desc" },
  { id: "dii", label: "DII", getValue: (m) => m.dii_holding_pct ?? 0, defaultDirection: "desc" },
];

export const GOLDEN_FILTER_SECTIONS: FilterSectionDef[] = [
  {
    title: "📈 Smart Filters (Increasing Holdings)",
    fields: [
      { type: "checkbox", id: "promoterIncreasing", label: "Promoter ↑", default: false },
      { type: "checkbox", id: "fiiIncreasing", label: "FII ↑", default: false },
      { type: "checkbox", id: "diiIncreasing", label: "DII ↑", default: false },
      { type: "checkbox", id: "mutualFundIncreasing", label: "Mutual Fund ↑", default: false },
    ],
  },
  {
    title: "🎚️ Holding Percentages",
    fields: [
      { type: "sliderMin", id: "promoterMin", label: "Promoter", min: 0, max: 100, default: 0 },
      { type: "sliderMin", id: "fiiMin", label: "FII", min: 0, max: 100, default: 0 },
      { type: "sliderMin", id: "diiMin", label: "DII", min: 0, max: 100, default: 0 },
      { type: "sliderMax", id: "retailMax", label: "Retail", min: 0, max: 100, default: 100 },
      { type: "sliderMin", id: "mutualFundMin", label: "Mutual Fund", min: 0, max: 100, default: 0 },
    ],
  },
  {
    title: "Advanced",
    fields: [
      { type: "marketCap", id: "marketCapFilter", default: "all" },
      { type: "select", id: "industry", label: "Industry", default: "all", options: [] },
    ],
  },
];

export const GOLDEN_ADVANCED_SECTION_TITLES = ["Advanced"];

export function applyGoldenFilters(
  matches: GoldenStockMatch[],
  values: FilterValues,
): GoldenStockMatch[] {
  return matches.filter((stock) => {
    const promoter = stock.promoter_holding_pct ?? 0;
    const fii = stock.fii_holding_pct ?? 0;
    const dii = stock.dii_holding_pct ?? 0;
    const retail = stock.retail_holding_pct ?? 0;
    const mutualFund = stock.mutual_fund_holding_pct ?? 0;

    if (promoter < Number(values.promoterMin)) return false;
    if (fii < Number(values.fiiMin)) return false;
    if (dii < Number(values.diiMin)) return false;
    if (retail > Number(values.retailMax)) return false;
    if (mutualFund < Number(values.mutualFundMin)) return false;

    const industry = String(values.industry ?? "all");
    if (industry !== "all" && stock.industry !== industry) return false;

    if (values.promoterIncreasing && stock.promoter_increasing !== true) return false;
    if (values.fiiIncreasing && stock.fii_increasing !== true) return false;
    if (values.diiIncreasing && stock.dii_increasing !== true) return false;
    if (values.mutualFundIncreasing && stock.mutual_fund_increasing !== true) return false;

    return true;
  });
}

export function buildGoldenIndustryOptions(
  matches: GoldenStockMatch[],
): { value: string; label: string }[] {
  const counts = new Map<string, number>();
  for (const m of matches) {
    if (m.industry) counts.set(m.industry, (counts.get(m.industry) ?? 0) + 1);
  }
  return Array.from(counts.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([ind, count]) => ({
      value: ind,
      label: `${ind} (${count})`,
    }));
}
