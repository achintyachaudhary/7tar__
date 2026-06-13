import { useCallback, useEffect, useState } from "react";
import { fetchUserPreferences, updateUserPreferences } from "../api";
import {
  purgeLegacyLocalOnlyKeys,
  readLocalCache,
  writeLocalCache,
} from "../lib/dbFirstStorage";

type Theme = "light" | "dark";

const CACHE_SUFFIX = "app_theme";
// Trading terminals default to dark; saved user preference still wins.
const DEFAULT_THEME: Theme = "dark";

function isTheme(value: unknown): value is Theme {
  return value === "light" || value === "dark";
}

function applyThemeToDom(theme: Theme) {
  document.documentElement.setAttribute("data-theme", theme);
}

async function loadThemeFromDatabase(): Promise<Theme | null> {
  const prefs = await fetchUserPreferences();
  const t = prefs.theme;
  return isTheme(t) ? t : null;
}

async function saveThemeToDatabase(theme: Theme): Promise<void> {
  await updateUserPreferences({ theme });
}

export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(DEFAULT_THEME);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let mounted = true;
    purgeLegacyLocalOnlyKeys();
    applyThemeToDom(DEFAULT_THEME);

    (async () => {
      let resolved: Theme = DEFAULT_THEME;
      try {
        const fromDb = await loadThemeFromDatabase();
        if (fromDb) {
          resolved = fromDb;
        } else {
          const cached = readLocalCache<string>(CACHE_SUFFIX);
          if (isTheme(cached)) {
            resolved = cached;
            await saveThemeToDatabase(cached);
          }
        }
        writeLocalCache(CACHE_SUFFIX, resolved);
      } catch {
        const cached = readLocalCache<string>(CACHE_SUFFIX);
        if (isTheme(cached)) resolved = cached;
      }

      if (mounted) {
        setTheme(resolved);
        applyThemeToDom(resolved);
        setReady(true);
      }
    })();

    return () => {
      mounted = false;
    };
  }, []);

  const toggle = useCallback(() => {
    if (!ready) return;
    const next: Theme = theme === "light" ? "dark" : "light";
    saveThemeToDatabase(next)
      .then(() => {
        setTheme(next);
        applyThemeToDom(next);
        writeLocalCache(CACHE_SUFFIX, next);
      })
      .catch((err) => {
        console.error("Failed to save theme to database:", err);
      });
  }, [theme, ready]);

  return [theme, toggle];
}
