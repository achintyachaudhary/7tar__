export interface CoreCriterion {
  id: string;
  label: string;
  detail?: string;
}

export interface ScanParamField {
  id: string;
  label: string;
  type: "number" | "boolean" | "select";
  default?: unknown;
  min?: number;
  max?: number;
  unit?: string;
  options?: string[];
}

export interface ScanDefinition {
  scan_type: string;
  name: string;
  description?: string;
  core_criteria: CoreCriterion[];
  param_schema: ScanParamField[];
}

export interface ScanConfigV1 {
  version: number;
  scan_type: string;
  name?: string;
  created_at?: string;
  core_criteria: CoreCriterion[];
  scan_params: Record<string, unknown>;
  display_filters: Record<string, unknown>;
  universe: {
    min_market_cap_cr?: number | null;
    max_market_cap_cr?: number | null;
  };
  last_scanned_at?: string | null;
  match_count?: number;
  legacy?: boolean;
}

export interface ScanProfileBundle {
  version: number;
  exported_at: string;
  app: string;
  profiles: ScanConfigV1[];
}
