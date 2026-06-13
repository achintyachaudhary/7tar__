import { useMemo } from "react";
import WeeklyInsightsPanel from "../components/WeeklyInsightsPanel";
import WeeklyStockRow from "../components/WeeklyStockRow";
import GenericFiltersPanel from "../components/GenericFiltersPanel";
import ScanPageToolbar from "../components/ScanPageToolbar";
import ScanActivitySection from "../components/ScanActivitySection";
import ScanCriteriaPanel from "../components/ScanCriteriaPanel";
import {
  applyWeeklyFilters,
  buildWeeklyIndustryOptions,
  WEEKLY_ADVANCED_SECTION_TITLES,
  WEEKLY_FILTER_SECTIONS,
  WEEKLY_SORT_OPTIONS,
} from "../config/weeklyPageConfig";
import { useScreenerPage } from "../hooks/useScreenerPage";
import { useSortState } from "../hooks/useSortState";
import { fetchWeeklyScanResults } from "../api";
import ActiveFiltersSummary from "../components/ActiveFiltersSummary";
import type { WeeklyStockMatch } from "../types/weekly";

export default function WeeklyStocksPage() {
  const screener = useScreenerPage<WeeklyStockMatch>({
    scanType: "weekly",
    filterSections: WEEKLY_FILTER_SECTIONS,
    applyFilters: applyWeeklyFilters,
    fetchCached: fetchWeeklyScanResults,
  });

  const sort = useSortState(WEEKLY_SORT_OPTIONS, { defaultId: "rank", multiSort: true });

  const filterSections = useMemo(() => {
    const industryOptions = [
      { value: "all", label: `All Industries (${screener.matches.length})` },
      ...buildWeeklyIndustryOptions(screener.matches),
    ];
    return WEEKLY_FILTER_SECTIONS.map((section) => {
      if (section.title !== "Advanced") return section;
      return {
        ...section,
        fields: section.fields.map((field) =>
          field.type === "select" && field.id === "industry"
            ? { ...field, options: industryOptions }
            : field,
        ),
      };
    });
  }, [screener.matches]);

  const filteredAndSortedMatches = useMemo(() => {
    return sort.applyTo(screener.filteredMatches);
  }, [screener.filteredMatches, sort.applyTo]);

  const progressPercent =
    screener.total > 0 ? Math.round((screener.scanned / screener.total) * 100) : 0;

  return (
    <div className="page-container weekly-stocks-page golden-stocks-page">
      <div className="page-header">
        <div>
          <h1>Weekly Stocks</h1>
          <p className="page-subtitle">
            Weekly price momentum plus growing financials.
          </p>
        </div>
      </div>

      <ScanCriteriaPanel
        definition={screener.definition}
        scanParams={screener.scanParams}
        onScanParamsChange={screener.setScanParams}
        onResetParams={screener.resetScanParams}
        onSaveParams={screener.persistScanParams}
        disabled={screener.scanning}
      />

      <WeeklyInsightsPanel
        matches={filteredAndSortedMatches}
        totalUnfiltered={screener.matches.length}
        onIndustryFilter={(ind) =>
          screener.setCosmeticFilters((prev) => ({ ...prev, industry: ind }))
        }
      />

      <ScanPageToolbar
        showFilters={screener.showFilters}
        onToggleFilters={() => screener.setShowFilters((v) => !v)}
        scanning={screener.scanning}
        onRunScan={screener.handleRunScan}
        onCancelScan={screener.cancelScan}
        sortOptions={WEEKLY_SORT_OPTIONS}
        sortStack={sort.stack}
        onSortToggle={sort.toggle}
        onClearSecondarySort={sort.clearSecondary}
        multiSort
      />

      {screener.showFilters && (
        <GenericFiltersPanel
          sections={filterSections}
          values={screener.cosmeticFilters}
          onChange={screener.setCosmeticFilters}
          onReset={screener.resetCosmeticFilters}
          disabled={screener.scanning}
          advancedSectionTitles={WEEKLY_ADVANCED_SECTION_TITLES}
        />
      )}

      <ActiveFiltersSummary
        sections={WEEKLY_FILTER_SECTIONS}
        values={screener.cosmeticFilters}
        onRemoveCosmeticFilter={screener.removeCosmeticFilter}
        scanConfig={screener.lastScanConfig}
        definition={screener.definition}
        totalMatches={screener.matches.length}
        filteredCount={filteredAndSortedMatches.length}
      />

      <ScanActivitySection
        scanning={screener.scanning}
        scanned={screener.scanned}
        total={screener.total}
        currentSymbol={screener.currentSymbol}
        progressPercent={progressPercent}
        matchCount={screener.matchCount}
        skippedCount={screener.skippedCount}
        startedAt={screener.scanStartedAt}
        error={screener.error}
        lastScannedAt={screener.lastScannedAt}
        logs={screener.scanLogs}
        alwaysShowProgress={screener.scanning || !!screener.error || !!screener.lastScannedAt}
        logTitle="Weekly Stocks scan log"
      />

      {!screener.scanning && screener.lastScannedAt && (
        <p className="scan-meta">
          {filteredAndSortedMatches.length} weekly
          {filteredAndSortedMatches.length !== screener.matches.length
            ? ` (of ${screener.matches.length} total from scan)`
            : ""}{" "}
          stocks
        </p>
      )}

      {screener.error && <div className="status error">{screener.error}</div>}

      {!screener.scanning &&
        !screener.error &&
        filteredAndSortedMatches.length === 0 &&
        screener.matches.length > 0 && (
          <div className="status">
            No stocks match your cosmetic filters ({screener.matches.length} from scan). Adjust
            filters or reset.
          </div>
        )}

      {!screener.scanning && !screener.error && screener.matches.length === 0 && (
        <div className="status">
          No weekly stocks found yet. Adjust core scanning parameters and run a scan.
        </div>
      )}

      <div className="golden-stock-list">
        {filteredAndSortedMatches.map((stock) => (
          <WeeklyStockRow
            key={stock.symbol}
            stock={stock}
            lastScannedAt={screener.lastScannedAt}
          />
        ))}
      </div>
    </div>
  );
}
