import { useCallback, useEffect, useMemo, useState } from "react";
import type { FilterSectionDef, FilterFieldDef } from "../components/GenericFiltersPanel";
import { getDefaultFilterValues } from "../components/GenericFiltersPanel";
import { fetchScanDefinition, saveScanParams } from "../api";
import {
  buildScanConfig,
  defaultScanParams,
  restoreFromScanConfig,
  scanConfigToStartPayload,
} from "../lib/scanConfig";
import type { FilterValues } from "../lib/filterSort";
import type { ScanConfigV1, ScanDefinition } from "../types/scanConfig";
import { useScanChannel, type ScanChannelState } from "./useScanChannel";
import { useGlobalScanMonitor } from "../context/GlobalScanMonitorContext";
import { useStockListsOptional } from "../context/StockListsContext";
import { normalizeListSymbol } from "../types/stockLists";

interface UseScreenerPageOptions<T> {
  scanType: string;
  filterSections: FilterSectionDef[];
  applyFilters: (matches: T[], values: FilterValues) => T[];
  fetchCached: () => Promise<{
    matches: T[] | unknown[];
    scanned: number;
    total: number;
    last_scanned_at: string | null;
    filter?: Record<string, unknown>;
  }>;
}

export function useScreenerPage<T>(options: UseScreenerPageOptions<T>) {
  const channel = useScanChannel<T>(options.scanType, {
    fetchCached: options.fetchCached,
  });
  const { getScan } = useGlobalScanMonitor();
  const monitor = getScan(options.scanType);
  const stockLists = useStockListsOptional();

  const [definition, setDefinition] = useState<ScanDefinition | null>(null);
  const [scanParams, setScanParams] = useState<Record<string, unknown>>({});
  const [cosmeticFilters, setCosmeticFilters] = useState<FilterValues>(() =>
    getDefaultFilterValues(options.filterSections),
  );
  const [showFilters, setShowFilters] = useState(false);

  useEffect(() => {
    fetchScanDefinition(options.scanType)
      .then((defn) => {
        setDefinition(defn);
        if (!channel.lastScanConfig) {
          setScanParams(defaultScanParams(defn));
        }
      })
      .catch(console.error);
  }, [options.scanType, channel.lastScanConfig]);

  useEffect(() => {
    if (!channel.lastScanConfig) return;
    const restored = restoreFromScanConfig(
      channel.lastScanConfig,
      options.filterSections,
    );
    setScanParams(restored.scanParams);
    setCosmeticFilters(restored.displayFilters);
  }, [channel.lastScanConfig, options.filterSections]);

  const filteredMatches = useMemo(() => {
    let list = options.applyFilters(channel.matches, cosmeticFilters);
    if (stockLists?.blacklistSet.size) {
      list = list.filter(
        (m) => !stockLists.blacklistSet.has(normalizeListSymbol(String((m as { symbol?: string }).symbol ?? ""))),
      );
    }
    return list;
  }, [channel.matches, cosmeticFilters, options.applyFilters, stockLists?.blacklistSet]);

  const currentScanConfig = useMemo(
    () =>
      buildScanConfig(
        options.scanType,
        definition,
        scanParams,
        cosmeticFilters,
      ),
    [options.scanType, definition, scanParams, cosmeticFilters],
  );

  const handleRunScan = useCallback(() => {
    const cfg = buildScanConfig(
      options.scanType,
      definition,
      scanParams,
      cosmeticFilters,
    );
    channel.startScan(scanConfigToStartPayload(cfg));
  }, [options.scanType, definition, scanParams, cosmeticFilters, channel.startScan]);

  const resetCosmeticFilters = useCallback(() => {
    setCosmeticFilters(getDefaultFilterValues(options.filterSections));
  }, [options.filterSections]);

  const removeCosmeticFilter = useCallback(
    (id: string, field: FilterFieldDef) => {
      setCosmeticFilters((prev) => ({ ...prev, [id]: field.default }));
    },
    [],
  );

  const resetScanParams = useCallback(() => {
    setScanParams(defaultScanParams(definition));
  }, [definition]);

  const persistScanParams = useCallback(async () => {
    const cfg = buildScanConfig(
      options.scanType,
      definition,
      scanParams,
      cosmeticFilters,
    );
    await saveScanParams(options.scanType, cfg);
  }, [options.scanType, definition, scanParams, cosmeticFilters]);

  const applyImportedConfig = useCallback(
    (cfg: ScanConfigV1) => {
      const restored = restoreFromScanConfig(cfg, options.filterSections);
      setScanParams(restored.scanParams);
      setCosmeticFilters(restored.displayFilters);
      channel.startScan(scanConfigToStartPayload(cfg));
    },
    [options.filterSections, channel.startScan],
  );

  return {
    ...channel,
    scanning: channel.scanning || monitor.scanning,
    scanned: monitor.scanning ? monitor.scanned : channel.scanned,
    total: monitor.scanning ? monitor.total : channel.total,
    currentSymbol: monitor.scanning ? monitor.currentSymbol : channel.currentSymbol,
    scanLogs: monitor.logs,
    matchCount: monitor.matchCount,
    skippedCount: monitor.skippedCount,
    scanStartedAt: monitor.startedAt,
    historyId: monitor.historyId,
    definition,
    scanParams,
    setScanParams,
    // Keep old names as aliases for backward compat within pages
    displayFilters: cosmeticFilters,
    setDisplayFilters: setCosmeticFilters,
    cosmeticFilters,
    setCosmeticFilters,
    showFilters,
    setShowFilters,
    filteredMatches,
    currentScanConfig,
    lastScanConfig: channel.lastScanConfig as ScanConfigV1 | null,
    handleRunScan,
    resetDisplayFilters: resetCosmeticFilters,
    resetCosmeticFilters,
    removeCosmeticFilter,
    resetScanParams,
    persistScanParams,
    applyImportedConfig,
  };
}

export type ScreenerPageState<T> = ReturnType<typeof useScreenerPage<T>> &
  ScanChannelState<T>;
