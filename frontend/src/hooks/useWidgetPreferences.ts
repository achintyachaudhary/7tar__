import { useCallback, useEffect, useRef, useState } from "react";
import { fetchWidgetPreferences, updateWidgetPreferences } from "../api";
import { readLocalCache, writeLocalCache } from "../lib/dbFirstStorage";
import type { WidgetPreferences } from "../types/widgetPreferences";

/**
 * Widget preferences: database (widget_preferences table) is the source of truth.
 * localStorage is updated only after a successful PUT, for offline display fallback.
 */
export function useWidgetPreferences(
  widgetId: string,
  defaultColumns: string[] = [],
) {
  const cacheSuffix = `widget_prefs:${widgetId}`;

  const [preferences, setPreferences] = useState<WidgetPreferences>({
    widget_id: widgetId,
    search_term: "",
    visible_columns: defaultColumns,
    column_filters: {},
  });
  const [loading, setLoading] = useState(true);
  const saveTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const preferencesRef = useRef(preferences);
  preferencesRef.current = preferences;

  useEffect(() => {
    let mounted = true;

    fetchWidgetPreferences(widgetId)
      .then((prefs) => {
        if (!mounted) return;
        const merged: WidgetPreferences = {
          ...prefs,
          visible_columns:
            prefs.visible_columns.length > 0 ? prefs.visible_columns : defaultColumns,
        };
        setPreferences(merged);
        writeLocalCache(cacheSuffix, merged);
      })
      .catch((err) => {
        console.error(`Failed to load preferences for ${widgetId} from database:`, err);
        const cached = readLocalCache<WidgetPreferences>(cacheSuffix);
        if (cached && mounted) {
          setPreferences({
            ...cached,
            widget_id: widgetId,
            visible_columns:
              cached.visible_columns?.length > 0
                ? cached.visible_columns
                : defaultColumns,
          });
        }
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });

    return () => {
      mounted = false;
    };
  }, [widgetId, defaultColumns, cacheSuffix]);

  const persistToDatabase = useCallback(
    async (prefs: WidgetPreferences) => {
      await updateWidgetPreferences(widgetId, {
        search_term: prefs.search_term,
        visible_columns: prefs.visible_columns,
        column_filters: prefs.column_filters,
      });
      writeLocalCache(cacheSuffix, prefs);
    },
    [widgetId, cacheSuffix],
  );

  const savePreferences = useCallback(
    (updates: Partial<WidgetPreferences>) => {
      const newPrefs = { ...preferencesRef.current, ...updates };
      setPreferences(newPrefs);

      if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current);
      saveTimeoutRef.current = setTimeout(() => {
        persistToDatabase(newPrefs).catch((err) => {
          console.error(`Failed to save preferences for ${widgetId} to database:`, err);
        });
      }, 1000);
    },
    [widgetId, persistToDatabase],
  );

  useEffect(() => {
    return () => {
      if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current);
    };
  }, []);

  const setSearchTerm = useCallback(
    (searchTerm: string) => {
      savePreferences({ search_term: searchTerm });
    },
    [savePreferences],
  );

  const setVisibleColumns = useCallback(
    (columns: string[]) => {
      savePreferences({ visible_columns: columns });
    },
    [savePreferences],
  );

  const setColumnFilters = useCallback(
    (filters: Record<string, unknown>) => {
      savePreferences({ column_filters: filters });
    },
    [savePreferences],
  );

  return {
    preferences,
    loading,
    setSearchTerm,
    setVisibleColumns,
    setColumnFilters,
    persistToDatabase,
  };
}
