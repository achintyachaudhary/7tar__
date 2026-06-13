import { useMemo, useState } from "react";
import type { ScanDefinition } from "../types/scanConfig";
import { describeScanParam } from "../lib/scanConfig";

interface ScanCriteriaPanelProps {
  definition: ScanDefinition | null;
  scanParams: Record<string, unknown>;
  onScanParamsChange: (params: Record<string, unknown>) => void;
  onResetParams?: () => void;
  onSaveParams?: () => Promise<void>;
  disabled?: boolean;
}

export default function ScanCriteriaPanel({
  definition,
  scanParams,
  onScanParamsChange,
  onResetParams,
  onSaveParams,
  disabled = false,
}: ScanCriteriaPanelProps) {
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const setParam = (id: string, value: unknown) => {
    setSaved(false);
    onScanParamsChange({ ...scanParams, [id]: value });
  };

  const handleSave = async () => {
    if (!onSaveParams) return;
    setSaving(true);
    setSaved(false);
    try {
      await onSaveParams();
      setSaved(true);
    } catch {
      setSaved(false);
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    setSaved(false);
    onResetParams?.();
  };

  const activeParams = useMemo(() => {
    if (!definition) return [];
    return definition.param_schema
      .map((f) => ({ field: f, desc: describeScanParam(f, scanParams[f.id]) }))
      .filter((x) => x.desc);
  }, [definition, scanParams]);

  if (!definition) return null;

  return (
    <div className="scan-criteria-panel">
      <h4 className="scan-criteria-heading">Core Scanning Parameters</h4>
      <p className="scan-criteria-hint">
        These control what the scanner looks for. Changes take effect on the next scan run.
      </p>

      <ul className="scan-criteria-core-list">
        {definition.core_criteria.map((c) => (
          <li key={c.id}>
            <span className="scan-criteria-core-label">{c.label}</span>
            {c.detail && <span className="scan-criteria-core-detail">{c.detail}</span>}
          </li>
        ))}
      </ul>

      <div className="scan-criteria-param-grid">
        {definition.param_schema.map((field) => {
          if (field.type === "boolean") {
            return (
              <label key={field.id} className="scan-criteria-param-bool">
                <input
                  type="checkbox"
                  checked={Boolean(scanParams[field.id] ?? field.default)}
                  onChange={(e) => setParam(field.id, e.target.checked)}
                  disabled={disabled}
                />
                <span>{field.label}</span>
              </label>
            );
          }
          if (field.type === "select") {
            return (
              <label key={field.id} className="scan-criteria-param-field">
                <span>{field.label}</span>
                <select
                  value={String(scanParams[field.id] ?? field.default ?? "")}
                  onChange={(e) => setParam(field.id, e.target.value)}
                  disabled={disabled}
                >
                  {(field.options ?? []).map((opt) => (
                    <option key={opt} value={opt}>
                      {opt}
                    </option>
                  ))}
                </select>
              </label>
            );
          }
          const v = Number(scanParams[field.id] ?? field.default ?? 0);
          const label =
            field.unit != null ? `${v} ${field.unit}` : String(v);
          return (
            <label key={field.id} className="scan-criteria-param-field">
              <span>
                {field.label}: {label}
              </span>
              <input
                type="range"
                min={field.min ?? 0}
                max={field.max ?? 100}
                step={field.unit === "%" ? 0.5 : 1}
                value={v}
                onChange={(e) => setParam(field.id, Number(e.target.value))}
                disabled={disabled}
              />
            </label>
          );
        })}
      </div>

      {activeParams.length > 0 && (
        <div className="scan-criteria-active-preview">
          <span className="scan-criteria-active-label">Active parameters:</span>
          {activeParams.map(({ field, desc }) => (
            <span key={field.id} className="active-filter-tag active-filter-tag-core-param">
              {desc}
            </span>
          ))}
        </div>
      )}

      {(onResetParams || onSaveParams) && (
        <div className="scan-criteria-actions">
          {onSaveParams && (
            <button
              type="button"
              className="toolbar-btn btn-primary"
              onClick={() => void handleSave()}
              disabled={disabled || saving}
            >
              {saving ? "Saving…" : "Save parameters"}
            </button>
          )}
          {onResetParams && (
            <button
              type="button"
              className="toolbar-btn"
              onClick={handleReset}
              disabled={disabled || saving}
            >
              Reset to default
            </button>
          )}
          {saved && <span className="scan-criteria-saved">✓ Saved to database</span>}
        </div>
      )}
    </div>
  );
}
