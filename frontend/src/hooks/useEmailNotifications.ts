import { useCallback, useEffect, useState } from "react";
import { fetchUserPreferences, updateUserPreferences } from "../api";
import {
  readLocalCache,
  writeLocalCache,
} from "../lib/dbFirstStorage";

const PREF_KEY = "email_notifications";
const CACHE_SUFFIX = "email_notifications";

function parseEnabled(value: unknown): boolean | null {
  if (value === "true" || value === true) return true;
  if (value === "false" || value === false) return false;
  return null;
}

async function loadFromDatabase(): Promise<boolean | null> {
  const prefs = await fetchUserPreferences();
  return parseEnabled(prefs[PREF_KEY]);
}

async function saveToDatabase(enabled: boolean): Promise<void> {
  await updateUserPreferences({ [PREF_KEY]: enabled ? "true" : "false" });
}

export function useEmailNotifications(): [boolean, () => void, boolean] {
  const [enabled, setEnabled] = useState(true);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let mounted = true;

    (async () => {
      let resolved = true;
      try {
        const fromDb = await loadFromDatabase();
        if (fromDb !== null) {
          resolved = fromDb;
        } else {
          const cached = readLocalCache<string>(CACHE_SUFFIX);
          const parsed = parseEnabled(cached);
          if (parsed !== null) {
            resolved = parsed;
            await saveToDatabase(parsed);
          }
        }
        writeLocalCache(CACHE_SUFFIX, resolved ? "true" : "false");
      } catch {
        const cached = readLocalCache<string>(CACHE_SUFFIX);
        const parsed = parseEnabled(cached);
        if (parsed !== null) resolved = parsed;
      }

      if (mounted) {
        setEnabled(resolved);
        setReady(true);
      }
    })();

    return () => {
      mounted = false;
    };
  }, []);

  const toggle = useCallback(() => {
    if (!ready) return;
    const next = !enabled;
    saveToDatabase(next)
      .then(() => {
        setEnabled(next);
        writeLocalCache(CACHE_SUFFIX, next ? "true" : "false");
      })
      .catch((err) => {
        console.error("Failed to save email notification preference:", err);
      });
  }, [enabled, ready]);

  return [enabled, toggle, ready];
}
