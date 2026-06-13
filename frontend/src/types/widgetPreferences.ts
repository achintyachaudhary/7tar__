export interface WidgetPreferences {
  widget_id: string;
  search_term: string;
  visible_columns: string[];
  column_filters: Record<string, any>;
  updated_at?: string | null;
}

export interface WidgetPreferencesUpdate {
  search_term?: string | null;
  visible_columns?: string[] | null;
  column_filters?: Record<string, any> | null;
}

/** Persisted in column_filters for widget_id live-trades-screener-sync */
export interface ScreenerSyncPrefs {
  enabled_screeners: string[];
  excluded_stocks: { symbol: string; source: string }[];
}
