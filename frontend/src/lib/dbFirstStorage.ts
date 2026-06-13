/**
 * Browser cache for preferences already stored in the database.
 * Rules: never treat localStorage as the source of truth; write only after a successful DB save.
 */

const CACHE_PREFIX = "db_cache:";

/** Keys that previously held scan data only in localStorage (removed — scans use scan_result_cache table). */
const LEGACY_LOCAL_ONLY_KEYS = [
  "brst_scan_cache",
  "multi_year_scan_cache",
  "golden_scan_cache",
  "weekly_scan_cache",
] as const;

interface ScanCacheEntry {
  matches: unknown[];
  scanned: number;
  total: number;
  last_scanned_at: string | null;
  cached_at: string;
}

export function cacheKey(suffix: string): string {
  return `${CACHE_PREFIX}${suffix}`;
}

export function readLocalCache<T>(suffix: string): T | null {
  try {
    const raw = localStorage.getItem(cacheKey(suffix));
    if (!raw) return null;
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

/** Call only after the server/database save succeeds. */
export function writeLocalCache(suffix: string, value: unknown): void {
  try {
    localStorage.setItem(cacheKey(suffix), JSON.stringify(value));
  } catch {
    // ignore quota / private mode
  }
}

export function removeLocalCache(suffix: string): void {
  try {
    localStorage.removeItem(cacheKey(suffix));
  } catch {
    // ignore
  }
}

/** Drop obsolete keys that were never synced to the database. */
export function purgeLegacyLocalOnlyKeys(): void {
  for (const key of LEGACY_LOCAL_ONLY_KEYS) {
    try {
      localStorage.removeItem(key);
    } catch {
      // ignore
    }
  }
  // Unprefixed theme key from older builds — migrate via useTheme, then use db_cache:app_theme
  try {
    const legacyTheme = localStorage.getItem("app_theme");
    if (legacyTheme === "light" || legacyTheme === "dark") {
      const cached = readLocalCache<string>("app_theme");
      if (!cached) writeLocalCache("app_theme", legacyTheme);
      localStorage.removeItem("app_theme");
    }
  } catch {
    // ignore
  }
}

// ── Scan result caching ───────────────────────────────────────────────────────

/**
 * Cache scan results in localStorage (DB-first: call only after backend fetch succeeds).
 */
export function cacheScanResults(scanType: string, data: {
  matches: unknown[];
  scanned: number;
  total: number;
  last_scanned_at: string | null;
}): void {
  const entry: ScanCacheEntry = {
    ...data,
    cached_at: new Date().toISOString(),
  };
  writeLocalCache(`scan_results:${scanType}`, entry);
}

/**
 * Read scan results from localStorage cache (used for instant display while fetching from backend).
 */
export function getCachedScanResults(scanType: string): ScanCacheEntry | null {
  return readLocalCache<ScanCacheEntry>(`scan_results:${scanType}`);
}
