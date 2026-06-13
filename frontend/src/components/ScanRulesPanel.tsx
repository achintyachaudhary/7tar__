import { useEffect, useState } from "react";
import { fetchScreeningRules } from "../api";
import type { ScreeningRule } from "../types/rules";

interface ScanRulesPanelProps {
  ruleId: string;
}

export default function ScanRulesPanel({ ruleId }: ScanRulesPanelProps) {
  const [open, setOpen] = useState(false);
  const [rule, setRule] = useState<ScreeningRule | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || rule) return;
    fetchScreeningRules()
      .then((data) => {
        const found = data.rules.find((r) => r.id === ruleId) ?? null;
        setRule(found);
        if (!found) setError("Rule not found");
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load rules"));
  }, [open, rule, ruleId]);

  const res = rule?.resistance;
  const vol = rule?.volume_confirmation;
  const groupBars = res?.test_grouping_bars ?? res?.test_grouping_weeks;
  const groupUnit = res?.test_grouping_bars != null ? "bars" : "weeks";

  return (
    <div className="scan-rules-panel">
      <button
        type="button"
        className="scan-rules-toggle"
        onClick={() => setOpen((o) => !o)}
        title="Show the screening rule currently applied"
      >
        {open ? "▾" : "▸"} Applied rule
      </button>

      {open && (
        <div className="scan-rules-body">
          {error && <div className="scan-rules-error">{error}</div>}
          {rule && (
            <>
              <div className="scan-rules-name">
                {rule.name}
                {rule.timeframe_label ? ` · ${rule.timeframe_label}` : ""}
              </div>
              {rule.description && <p className="scan-rules-desc">{rule.description}</p>}
              <ul className="scan-rules-list">
                {res?.max_distance_from_high_pct != null && (
                  <li>Within <strong>{res.max_distance_from_high_pct}%</strong> of the period high</li>
                )}
                {res?.min_distinct_tests != null && (
                  <li>
                    At least <strong>{res.min_distinct_tests}</strong> tests of resistance
                    {res.test_zone_pct != null ? ` (within ${res.test_zone_pct}% of the high)` : ""}
                    {groupBars != null ? `, grouped within ${groupBars} ${groupUnit}` : ""}
                  </li>
                )}
                {vol?.enabled && (
                  <li>
                    Volume confirmed when recent volume ≥{" "}
                    <strong>{vol.min_breakout_volume_multiple}×</strong> the{" "}
                    {vol.average_window_days}-day average{" "}
                    {vol.require_for_match ? "(required)" : "(flagged, not required)"}
                  </li>
                )}
              </ul>
              <div className="scan-rules-hint">
                Edit these in <code>Backend/app/rules/{rule.id}.json</code>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
