import { useMemo } from "react";
import type { FilterSectionDef, FilterFieldDef } from "./GenericFiltersPanel";
import type { FilterValues } from "../lib/filterSort";
import type { MarketCapFilterValue } from "./MarketCapFilterSelect";
import type { ScanConfigV1, ScanDefinition } from "../types/scanConfig";
import { describeScanParam } from "../lib/scanConfig";

const MARKET_CAP_LABELS: Record<string, string> = {
  all: "All Market Caps",
  micro: "Micro Cap (< ₹500 Cr)",
  small: "Small Cap (₹500–₹5K Cr)",
  mid: "Mid Cap (₹5K–₹20K Cr)",
  large: "Large Cap (₹20K–₹1L Cr)",
  mega: "Mega Cap (> ₹1L Cr)",
};

interface ActiveTag {
  id: string;
  label: string;
}

function describeCosmeticFilter(field: FilterFieldDef, value: unknown): string | null {
  switch (field.type) {
    case "checkbox":
      return value ? field.label : null;
    case "sliderMin": {
      const v = Number(value ?? field.default);
      if (v <= field.min) return null;
      return field.format ? `${field.label}: ${field.format(v)}` : `${field.label} \u2265 ${v}%`;
    }
    case "sliderMax": {
      const v = Number(value ?? field.default);
      if (v >= field.max) return null;
      return field.format ? `${field.label}: ${field.format(v)}` : `${field.label} \u2264 ${v}%`;
    }
    case "select": {
      const v = String(value ?? field.default);
      if (v === "all" || v === field.default) return null;
      const opt = field.options.find((o) => o.value === v);
      return `${field.label}: ${opt?.label ?? v}`;
    }
    case "marketCap": {
      const v = (value as MarketCapFilterValue) ?? field.default;
      if (v === "all") return null;
      return MARKET_CAP_LABELS[v] ?? v;
    }
    default:
      return null;
  }
}

function collectCosmeticTags(
  sections: FilterSectionDef[],
  values: FilterValues,
): ActiveTag[] {
  const result: ActiveTag[] = [];
  for (const section of sections) {
    for (const field of section.fields) {
      const desc = describeCosmeticFilter(field, values[field.id]);
      if (desc) result.push({ id: field.id, label: desc });
    }
  }
  return result;
}

interface ActiveFiltersSummaryProps {
  sections: FilterSectionDef[];
  values: FilterValues;
  onRemoveCosmeticFilter?: (id: string, field: FilterFieldDef) => void;
  scanConfig?: ScanConfigV1 | null;
  definition?: ScanDefinition | null;
  totalMatches: number;
  filteredCount: number;
}

export default function ActiveFiltersSummary({
  sections,
  values,
  onRemoveCosmeticFilter,
  scanConfig,
  definition,
  totalMatches,
  filteredCount,
}: ActiveFiltersSummaryProps) {
  const cosmeticTags = useMemo(
    () => collectCosmeticTags(sections, values),
    [sections, values],
  );

  const coreParamTags = useMemo(() => {
    const def = definition;
    const params = scanConfig?.scan_params;
    if (!def || !params) return [];
    return def.param_schema
      .map((f): ActiveTag | null => {
        if (!(f.id in params)) return null;
        const desc = describeScanParam(f, params[f.id]);
        if (!desc) return null;
        return { id: f.id, label: desc };
      })
      .filter((d): d is ActiveTag => Boolean(d));
  }, [definition, scanConfig]);

  const hasCoreParams = coreParamTags.length > 0;
  const hasCosmetic = cosmeticTags.length > 0;
  const isFiltered = filteredCount < totalMatches;

  if (!hasCoreParams && !hasCosmetic && !isFiltered) return null;

  const findField = (id: string): FilterFieldDef | undefined => {
    for (const sec of sections) {
      const f = sec.fields.find((field) => field.id === id);
      if (f) return f;
    }
    return undefined;
  };

  return (
    <div className="active-filters-bar">
      {hasCoreParams && (
        <div className="active-filters-group">
          <span className="active-filters-group-label">Scanned with</span>
          <div className="active-filters-tags">
            {coreParamTags.map((tag) => (
              <span key={tag.id} className="active-filter-chip core-param">
                {tag.label}
              </span>
            ))}
          </div>
        </div>
      )}

      {hasCosmetic && (
        <div className="active-filters-group">
          <span className="active-filters-group-label">Cosmetic Filters</span>
          <div className="active-filters-tags">
            {cosmeticTags.map((tag) => {
              const field = findField(tag.id);
              return (
                <span key={tag.id} className="active-filter-chip cosmetic">
                  {tag.label}
                  {onRemoveCosmeticFilter && field && (
                    <button
                      type="button"
                      className="active-filter-chip-remove"
                      onClick={() => onRemoveCosmeticFilter(tag.id, field)}
                      title={`Remove ${tag.label}`}
                    >
                      ×
                    </button>
                  )}
                </span>
              );
            })}
          </div>
        </div>
      )}

      {isFiltered && (
        <span className="active-filters-count-label">
          Showing {filteredCount} of {totalMatches}
        </span>
      )}
    </div>
  );
}
