import type { FilterSectionDef } from "../components/GenericFiltersPanel";
import type { SortOption } from "../lib/filterSort";
import type { BrStMatch } from "../types/brst";
import type { MultiYearMatch } from "../types/multiYear";
import type { FilterValues } from "../lib/filterSort";

export type BreakoutMatch = BrStMatch | MultiYearMatch;

export const BREAKOUT_SORT_OPTIONS: SortOption<BreakoutMatch>[] = [
  {
    id: "tests",
    label: "Tests",
    getValue: (m) => m.tests_count,
    defaultDirection: "desc",
  },
  { id: "price", label: "Price", getValue: (m) => m.price, defaultDirection: "desc" },
  {
    id: "distance",
    label: "Distance",
    getValue: (m) => m.distance_pct,
    defaultDirection: "asc",
  },
  {
    id: "resistance",
    label: "Resistance",
    getValue: (m) => m.highest_high,
    defaultDirection: "desc",
  },
];

export const BREAKOUT_FILTER_SECTIONS: FilterSectionDef[] = [
  {
    title: "Cosmetic Filters",
    fields: [
      { type: "marketCap", id: "marketCapFilter", default: "all" },
    ],
  },
  {
    title: "Result thresholds",
    fields: [
      {
        type: "sliderMin",
        id: "minTests",
        label: "Min tests",
        min: 0,
        max: 20,
        default: 0,
        format: (v: number) => `≥ ${v}`,
      },
      {
        type: "sliderMax",
        id: "maxDistance",
        label: "Max distance from high",
        min: 0,
        max: 10,
        default: 10,
        format: (v) => `≤ ${v}%`,
      },
    ],
  },
];

export function applyBreakoutFilters(
  matches: BreakoutMatch[],
  values: FilterValues,
): BreakoutMatch[] {
  return matches.filter((m) => {
    if (m.tests_count < Number(values.minTests ?? 0)) return false;
    if (m.distance_pct > Number(values.maxDistance ?? 10)) return false;
    return true;
  });
}
