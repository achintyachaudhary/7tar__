import type { FilterSectionDef } from "../components/GenericFiltersPanel";
import type { FilterValues, SortOption } from "../lib/filterSort";
import type { VolumeSurgeMatch } from "../types/volumeSurge";

export const VOLUME_SURGE_SORT_OPTIONS: SortOption<VolumeSurgeMatch>[] = [
  {
    id: "volume_multiple",
    label: "Volume multiple",
    getValue: (m) => m.volume_multiple,
    defaultDirection: "desc",
  },
  {
    id: "day_change",
    label: "Day change %",
    getValue: (m) => m.day_change_pct,
    defaultDirection: "desc",
  },
  {
    id: "close_strength",
    label: "Close strength",
    getValue: (m) => m.close_strength_pct,
    defaultDirection: "desc",
  },
  { id: "price", label: "Price", getValue: (m) => m.price, defaultDirection: "desc" },
];

export const VOLUME_SURGE_FILTER_SECTIONS: FilterSectionDef[] = [
  {
    title: "Cosmetic Filters",
    fields: [
      { type: "marketCap", id: "marketCapFilter", default: "all" },
      {
        type: "sliderMin",
        id: "minMultiple",
        label: "Min volume multiple",
        min: 0,
        max: 10,
        default: 0,
        format: (v: number) => `≥ ${v}×`,
      },
      {
        type: "sliderMin",
        id: "minDayChange",
        label: "Min day change",
        min: 0,
        max: 15,
        default: 0,
        format: (v: number) => `≥ ${v}%`,
      },
    ],
  },
];

export function applyVolumeSurgeFilters(
  matches: VolumeSurgeMatch[],
  values: FilterValues,
): VolumeSurgeMatch[] {
  return matches.filter((m) => {
    if (m.volume_multiple < Number(values.minMultiple ?? 0)) return false;
    if (m.day_change_pct < Number(values.minDayChange ?? 0)) return false;
    return true;
  });
}
