import type { FilterSectionDef } from "../components/GenericFiltersPanel";
import type { FilterValues, SortOption } from "../lib/filterSort";
import type { DarvasMatch } from "../types/darvas";

export const DARVAS_SORT_OPTIONS: SortOption<DarvasMatch>[] = [
  {
    id: "breakout",
    label: "Breakout %",
    getValue: (m) => m.breakout_pct,
    defaultDirection: "asc",
  },
  { id: "price", label: "Price", getValue: (m) => m.price, defaultDirection: "desc" },
  {
    id: "box_range",
    label: "Box Range %",
    getValue: (m) => m.box_range_pct,
    defaultDirection: "asc",
  },
  {
    id: "boxes",
    label: "Boxes Found",
    getValue: (m) => m.boxes_count,
    defaultDirection: "desc",
  },
];

export const DARVAS_FILTER_SECTIONS: FilterSectionDef[] = [
  {
    title: "Cosmetic Filters",
    fields: [
      { type: "marketCap", id: "marketCapFilter", default: "all" },
      {
        type: "sliderMax",
        id: "maxBreakout",
        label: "Max breakout %",
        min: 0,
        max: 10,
        default: 10,
        format: (v: number) => `≤ ${v}%`,
      },
      {
        type: "sliderMax",
        id: "maxBoxRange",
        label: "Max box range %",
        min: 0,
        max: 15,
        default: 15,
        format: (v: number) => `≤ ${v}%`,
      },
    ],
  },
];

export function applyDarvasFilters(
  matches: DarvasMatch[],
  values: FilterValues,
): DarvasMatch[] {
  return matches.filter((m) => {
    if (m.breakout_pct > Number(values.maxBreakout ?? 10)) return false;
    if (m.box_range_pct > Number(values.maxBoxRange ?? 15)) return false;
    return true;
  });
}
