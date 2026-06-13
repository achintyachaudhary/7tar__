import type { FilterSectionDef } from "../components/GenericFiltersPanel";
import type { FilterValues, SortOption } from "../lib/filterSort";
import type { VolSqueezeMatch } from "../types/volSqueeze";

export const VOL_SQUEEZE_SORT_OPTIONS: SortOption<VolSqueezeMatch>[] = [
  {
    id: "atr_ratio",
    label: "Tightest squeeze",
    getValue: (m) => m.atr_ratio,
    defaultDirection: "asc",
  },
  {
    id: "range",
    label: "Range %",
    getValue: (m) => m.range_pct,
    defaultDirection: "asc",
  },
  {
    id: "dist_high",
    label: "Distance from range high",
    getValue: (m) => m.dist_from_range_high_pct,
    defaultDirection: "asc",
  },
  { id: "price", label: "Price", getValue: (m) => m.price, defaultDirection: "desc" },
];

export const VOL_SQUEEZE_FILTER_SECTIONS: FilterSectionDef[] = [
  {
    title: "Cosmetic Filters",
    fields: [
      { type: "marketCap", id: "marketCapFilter", default: "all" },
      {
        type: "sliderMax",
        id: "maxRange",
        label: "Max range %",
        min: 0,
        max: 20,
        default: 20,
        format: (v: number) => `≤ ${v}%`,
      },
      {
        type: "sliderMax",
        id: "maxDistHigh",
        label: "Max distance from range high",
        min: 0,
        max: 15,
        default: 15,
        format: (v: number) => `≤ ${v}%`,
      },
    ],
  },
];

export function applyVolSqueezeFilters(
  matches: VolSqueezeMatch[],
  values: FilterValues,
): VolSqueezeMatch[] {
  return matches.filter((m) => {
    if (m.range_pct > Number(values.maxRange ?? 20)) return false;
    if (m.dist_from_range_high_pct > Number(values.maxDistHigh ?? 15)) return false;
    return true;
  });
}
