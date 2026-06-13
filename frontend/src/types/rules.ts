export interface ScreeningRuleResistance {
  max_distance_from_high_pct?: number;
  test_zone_pct?: number;
  min_distinct_tests?: number;
  test_grouping_bars?: number;
  test_grouping_weeks?: number;
}

export interface ScreeningRuleVolume {
  enabled?: boolean;
  average_window_days?: number;
  recent_lookback_days?: number;
  min_breakout_volume_multiple?: number;
  require_for_match?: boolean;
}

export interface ScreeningRule {
  id: string;
  name: string;
  timeframe_label?: string;
  description?: string;
  data?: Record<string, unknown>;
  resistance?: ScreeningRuleResistance;
  volume_confirmation?: ScreeningRuleVolume;
}
