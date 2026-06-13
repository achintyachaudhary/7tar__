import type { FilterSectionDef } from "../components/GenericFiltersPanel";
import type { FilterValues, SortOption } from "../lib/filterSort";
import type { MeanReversionMatch } from "../types/meanReversion";

export const MEAN_REVERSION_SORT_OPTIONS: SortOption<MeanReversionMatch>[] = [
  {
    id: "rr",
    label: "Reward : Risk",
    getValue: (m) => m.reward_risk,
    defaultDirection: "desc",
  },
  { id: "rsi", label: "RSI", getValue: (m) => m.rsi, defaultDirection: "asc" },
  {
    id: "pullback",
    label: "Pullback %",
    getValue: (m) => m.pullback_pct,
    defaultDirection: "desc",
  },
  { id: "price", label: "Price", getValue: (m) => m.price, defaultDirection: "desc" },
];

export const MEAN_REVERSION_FILTER_SECTIONS: FilterSectionDef[] = [
  {
    title: "Cosmetic Filters",
    fields: [
      { type: "marketCap", id: "marketCapFilter", default: "all" },
      {
        type: "sliderMax",
        id: "maxRsi",
        label: "Max RSI",
        min: 0,
        max: 50,
        default: 50,
        format: (v: number) => `≤ ${v}`,
      },
      {
        type: "sliderMin",
        id: "minRr",
        label: "Min reward : risk",
        min: 0,
        max: 5,
        default: 0,
        format: (v: number) => `≥ ${v}:1`,
      },
    ],
  },
];

export function applyMeanReversionFilters(
  matches: MeanReversionMatch[],
  values: FilterValues,
): MeanReversionMatch[] {
  return matches.filter((m) => {
    if (m.rsi > Number(values.maxRsi ?? 50)) return false;
    if (m.reward_risk < Number(values.minRr ?? 0)) return false;
    return true;
  });
}
