import { useState } from "react";
import MarketCapFilterSelect, {
  type MarketCapFilterValue,
} from "./MarketCapFilterSelect";
import type { FilterValues } from "../lib/filterSort";

export type FilterFieldDef =
  | {
      type: "checkbox";
      id: string;
      label: string;
      default: boolean;
    }
  | {
      type: "sliderMin";
      id: string;
      label: string;
      min: number;
      max: number;
      default: number;
      format?: (value: number) => string;
    }
  | {
      type: "sliderMax";
      id: string;
      label: string;
      min: number;
      max: number;
      default: number;
      format?: (value: number) => string;
    }
  | {
      type: "select";
      id: string;
      label: string;
      default: string;
      options: { value: string; label: string }[];
    }
  | {
      type: "marketCap";
      id: string;
      label?: string;
      default: MarketCapFilterValue;
    };

export interface FilterSectionDef {
  title?: string;
  fields: FilterFieldDef[];
}

interface GenericFiltersPanelProps {
  title?: string;
  sections: FilterSectionDef[];
  values: FilterValues;
  onChange: (values: FilterValues) => void;
  onReset: () => void;
  disabled?: boolean;
  advancedSectionTitles?: string[];
}

function renderField(
  field: FilterFieldDef,
  values: FilterValues,
  onChange: (values: FilterValues) => void,
  disabled: boolean,
) {
  const set = (id: string, value: boolean | number | string) => {
    onChange({ ...values, [id]: value });
  };

  switch (field.type) {
    case "checkbox":
      return (
        <label key={field.id} className="filter-checkbox">
          <input
            type="checkbox"
            checked={Boolean(values[field.id])}
            onChange={(e) => set(field.id, e.target.checked)}
            disabled={disabled}
          />
          <span>{field.label}</span>
        </label>
      );

    case "sliderMin": {
      const v = Number(values[field.id] ?? field.default);
      const label = field.format ? field.format(v) : `\u2265 ${v}%`;
      return (
        <div key={field.id} className="filter-slider-group">
          <label>
            {field.label}: {label}
          </label>
          <input
            type="range"
            min={field.min}
            max={field.max}
            value={v}
            onChange={(e) => set(field.id, Number(e.target.value))}
            disabled={disabled}
          />
        </div>
      );
    }

    case "sliderMax": {
      const v = Number(values[field.id] ?? field.default);
      const label = field.format ? field.format(v) : `\u2264 ${v}%`;
      return (
        <div key={field.id} className="filter-slider-group">
          <label>
            {field.label}: {label}
          </label>
          <input
            type="range"
            min={field.min}
            max={field.max}
            value={v}
            onChange={(e) => set(field.id, Number(e.target.value))}
            disabled={disabled}
          />
        </div>
      );
    }

    case "select":
      return (
        <div key={field.id} className="filter-group">
          <label>{field.label}</label>
          <select
            value={String(values[field.id] ?? field.default)}
            onChange={(e) => set(field.id, e.target.value)}
            disabled={disabled}
          >
            {field.options.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
      );

    case "marketCap":
      return (
        <div key={field.id} className="filter-group">
          <label>{field.label ?? "Market Cap"}</label>
          <MarketCapFilterSelect
            value={(values[field.id] as MarketCapFilterValue) ?? field.default}
            onChange={(val) => set(field.id, val)}
            disabled={disabled}
          />
        </div>
      );

    default:
      return null;
  }
}

export function getDefaultFilterValues(sections: FilterSectionDef[]): FilterValues {
  const values: FilterValues = {};
  for (const section of sections) {
    for (const field of section.fields) {
      values[field.id] = field.default;
    }
  }
  return values;
}

export default function GenericFiltersPanel({
  title = "Cosmetic Filters",
  sections,
  values,
  onChange,
  onReset,
  disabled = false,
  advancedSectionTitles = [],
}: GenericFiltersPanelProps) {
  const [showAdvanced, setShowAdvanced] = useState(false);

  const primarySections = sections.filter(
    (s) => !s.title || !advancedSectionTitles.includes(s.title),
  );
  const advancedSections = sections.filter(
    (s) => s.title && advancedSectionTitles.includes(s.title),
  );
  const hasAdvanced = advancedSections.length > 0;

  const renderSection = (section: FilterSectionDef) => (
    <div key={section.title ?? "default"} className="filter-section">
      {section.title && <h4 className="filter-section-title">{section.title}</h4>}
      {section.fields.some((f) => f.type === "checkbox") ? (
        <div className="filter-checkboxes">
          {section.fields
            .filter((f) => f.type === "checkbox")
            .map((f) => renderField(f, values, onChange, disabled))}
        </div>
      ) : null}
      {section.fields
        .filter((f) => f.type !== "checkbox")
        .map((f) => renderField(f, values, onChange, disabled))}
    </div>
  );

  return (
    <div className="cosmetic-filters-panel filters-panel generic-filters-panel">
      <div className="cosmetic-filters-header">
        <h3>{title}</h3>
        <span className="cosmetic-filters-hint">
          Narrow down results without re-scanning
        </span>
        <button type="button" className="filter-reset-btn" onClick={onReset}>
          Reset All
        </button>
      </div>

      {primarySections.map(renderSection)}

      {hasAdvanced && (
        <>
          <button
            type="button"
            className="filter-toggle-advanced"
            onClick={() => setShowAdvanced(!showAdvanced)}
          >
            {showAdvanced ? "▼" : "▶"} Advanced Filters
          </button>
          {showAdvanced && advancedSections.map(renderSection)}
        </>
      )}
    </div>
  );
}
