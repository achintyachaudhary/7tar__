import { useState, useCallback } from "react";
import type { ScanSchedule } from "../api";
import TimestampLabel from "./TimestampLabel";

interface ScheduleConfigFormProps {
  schedule: ScanSchedule;
  onSave: (config: {
    enabled: boolean;
    frequency: string;
    time_of_day: string;
    timezone: string;
  }) => Promise<void>;
}

const SCAN_TYPE_LABELS: Record<string, string> = {
  nse_stocks: "NSE Stocks",
  brst: "Year Breakout",
  multi_year: "Multi-Year Breakout",
  golden: "Golden Stocks",
  weekly: "Weekly Stocks",
};

export default function ScheduleConfigForm({ schedule, onSave }: ScheduleConfigFormProps) {
  const [enabled, setEnabled] = useState(schedule.enabled);
  const [frequency, setFrequency] = useState(schedule.frequency);
  const [timeOfDay, setTimeOfDay] = useState(schedule.time_of_day);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const hasChanges =
    enabled !== schedule.enabled ||
    frequency !== schedule.frequency ||
    timeOfDay !== schedule.time_of_day;

  const handleSave = useCallback(async () => {
    setSaving(true);
    setError(null);
    try {
      await onSave({
        enabled,
        frequency,
        time_of_day: timeOfDay,
        timezone: schedule.timezone,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save schedule");
    } finally {
      setSaving(false);
    }
  }, [enabled, frequency, timeOfDay, schedule.timezone, onSave]);

  const handleReset = useCallback(() => {
    setEnabled(schedule.enabled);
    setFrequency(schedule.frequency);
    setTimeOfDay(schedule.time_of_day);
    setError(null);
  }, [schedule]);

  const scanLabel = SCAN_TYPE_LABELS[schedule.scan_type] || schedule.scan_type;

  return (
    <div className="schedule-config-form">
      <div className="schedule-config-header">
        <div>
          <h3 className="schedule-config-title">{scanLabel}</h3>
          <TimestampLabel at={schedule.updated_at} label="Last saved" />
        </div>
        <label className="schedule-config-toggle">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
          />
          <span className="schedule-config-toggle-label">
            {enabled ? "Enabled" : "Disabled"}
          </span>
        </label>
      </div>

      <div className="schedule-config-fields">
        <div className="schedule-config-field">
          <label className="schedule-config-label">Frequency</label>
          <select
            value={frequency}
            onChange={(e) => setFrequency(e.target.value)}
            className="schedule-config-select"
          >
            <option value="daily">Daily</option>
            <option value="weekly">Weekly (Monday)</option>
          </select>
        </div>

        <div className="schedule-config-field">
          <label className="schedule-config-label">Time (IST)</label>
          <input
            type="time"
            value={timeOfDay}
            onChange={(e) => setTimeOfDay(e.target.value)}
            className="schedule-config-input"
          />
        </div>
      </div>

      {error && <div className="schedule-config-error">{error}</div>}

      <div className="schedule-config-actions">
        <button
          type="button"
          onClick={handleReset}
          disabled={!hasChanges || saving}
          className="schedule-config-btn schedule-config-btn-reset"
        >
          Reset
        </button>
        <button
          type="button"
          onClick={handleSave}
          disabled={!hasChanges || saving}
          className="schedule-config-btn schedule-config-btn-save"
        >
          {saving ? "Saving…" : "Save"}
        </button>
      </div>
    </div>
  );
}
