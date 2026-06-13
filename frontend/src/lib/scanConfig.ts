import { marketCapFilterToApi } from "../components/MarketCapFilterSelect";
import type { FilterSectionDef } from "../components/GenericFiltersPanel";
import { getDefaultFilterValues } from "../components/GenericFiltersPanel";
import type { FilterValues } from "./filterSort";
import type { ScanConfigV1, ScanDefinition, ScanProfileBundle } from "../types/scanConfig";

export const SCAN_CONFIG_VERSION = 1;
export const EXPORT_BUNDLE_VERSION = 1;

export function defaultScanParams(defn: ScanDefinition | null): Record<string, unknown> {
  if (!defn) return {};
  const out: Record<string, unknown> = {};
  for (const f of defn.param_schema) {
    out[f.id] = f.default;
  }
  return out;
}

export function buildScanConfig(
  scanType: string,
  defn: ScanDefinition | null,
  scanParams: Record<string, unknown>,
  displayFilters: FilterValues,
): ScanConfigV1 {
  const cap = marketCapFilterToApi(
    (displayFilters.marketCapFilter ?? "all") as Parameters<typeof marketCapFilterToApi>[0],
  );
  return {
    version: SCAN_CONFIG_VERSION,
    scan_type: scanType,
    name: defn?.name ?? scanType,
    created_at: new Date().toISOString(),
    core_criteria: defn?.core_criteria ?? [],
    scan_params: { ...scanParams },
    display_filters: { ...displayFilters },
    universe: {
      min_market_cap_cr: cap.min_market_cap_cr ?? null,
      max_market_cap_cr: cap.max_market_cap_cr ?? null,
    },
  };
}

export function scanConfigToStartPayload(cfg: ScanConfigV1): Record<string, unknown> {
  const cap = cfg.universe ?? {};
  return {
    scan_config: cfg,
    min_market_cap_cr: cap.min_market_cap_cr,
    max_market_cap_cr: cap.max_market_cap_cr,
    require_volume_confirmation: cfg.scan_params?.require_volume_confirmation,
    ui_filters: cfg.display_filters,
  };
}

export function parseProfileBundle(raw: string): {
  bundle: ScanProfileBundle | null;
  errors: string[];
} {
  try {
    const data = JSON.parse(raw) as ScanProfileBundle;
    const errors: string[] = [];
    if (data.version !== EXPORT_BUNDLE_VERSION) {
      errors.push(`Unsupported bundle version ${data.version}`);
    }
    if (!Array.isArray(data.profiles)) {
      errors.push("Missing profiles array");
      return { bundle: null, errors };
    }
    return { bundle: data, errors };
  } catch {
    return { bundle: null, errors: ["Invalid JSON file"] };
  }
}

export function restoreFromScanConfig(
  cfg: ScanConfigV1 | null,
  filterSections: FilterSectionDef[],
): {
  scanParams: Record<string, unknown>;
  displayFilters: FilterValues;
} {
  const base = getDefaultFilterValues(filterSections);
  if (!cfg) {
    return { scanParams: {}, displayFilters: base };
  }
  return {
    scanParams: { ...(cfg.scan_params ?? {}) },
    displayFilters: { ...base, ...(cfg.display_filters as FilterValues) },
  };
}

export function describeScanParam(
  field: ScanDefinition["param_schema"][0],
  value: unknown,
): string | null {
  if (field.type === "boolean") {
    return value ? field.label : null;
  }
  if (field.type === "select") {
    const v = String(value ?? field.default);
    return `${field.label}: ${v}`;
  }
  const v = Number(value ?? field.default);
  if (field.default != null && v === Number(field.default)) return null;
  const unit = field.unit ? ` ${field.unit}` : "";
  return `${field.label}: ${v}${unit}`;
}
