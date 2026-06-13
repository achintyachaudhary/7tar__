import { useMemo } from "react";
import GoldenInsightsPanel from "../components/GoldenInsightsPanel";
import GoldenStockRow from "../components/GoldenStockRow";
import GenericFiltersPanel from "../components/GenericFiltersPanel";
import ScanPageToolbar from "../components/ScanPageToolbar";
import ScanActivitySection from "../components/ScanActivitySection";
import ScanCriteriaPanel from "../components/ScanCriteriaPanel";
import {
  applyGoldenFilters,
  buildGoldenIndustryOptions,
  GOLDEN_ADVANCED_SECTION_TITLES,
  GOLDEN_FILTER_SECTIONS,
  GOLDEN_SORT_OPTIONS,
} from "../config/goldenPageConfig";
import { useScreenerPage } from "../hooks/useScreenerPage";
import { useSortState } from "../hooks/useSortState";
import { fetchGoldenScanResults } from "../api";
import ActiveFiltersSummary from "../components/ActiveFiltersSummary";
import type { GoldenStockMatch } from "../types/golden";

export default function GoldenStocksPage() {
  const screener = useScreenerPage<GoldenStockMatch>({
    scanType: "golden",
    filterSections: GOLDEN_FILTER_SECTIONS,
    applyFilters: applyGoldenFilters,
    fetchCached: fetchGoldenScanResults,
  });

  const sort = useSortState(GOLDEN_SORT_OPTIONS, { defaultId: "rank", multiSort: true });

  const filterSections = useMemo(() => {
    const industryOptions = [
      { value: "all", label: `All Industries (${screener.matches.length})` },
      ...buildGoldenIndustryOptions(screener.matches),
    ];
    return GOLDEN_FILTER_SECTIONS.map((section) => {
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

  const filteredAndSortedMatches = useMemo(
    () => sort.applyTo(screener.filteredMatches),
    [screener.filteredMatches, sort.applyTo],
  );

  const progressPercent =
    screener.total > 0 ? Math.round((screener.scanned / screener.total) * 100) : 0;

  return (
    <div className="page-container golden-stocks-page">
      <div className="page-header">
        <div>
          <h1>Golden Stocks</h1>
          <p className="page-subtitle">
            Price, revenue, and profit momentum with holdings quality ranking.
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

      <GoldenInsightsPanel
        matches={filteredAndSortedMatches}
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
        sortOptions={GOLDEN_SORT_OPTIONS}
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
          advancedSectionTitles={GOLDEN_ADVANCED_SECTION_TITLES}
        />
      )}

      <ActiveFiltersSummary
        sections={GOLDEN_FILTER_SECTIONS}
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
        logTitle="Golden Stocks scan log"
      />

      {!screener.scanning && screener.lastScannedAt && (
        <p className="scan-meta">
          {filteredAndSortedMatches.length} golden
          {filteredAndSortedMatches.length !== screener.matches.length
            ? ` (of ${screener.matches.length} total from scan)`
            : ""}{" "}
          stocks
        </p>
      )}

      {screener.error && <div className="status error">{screener.error}</div>}

      {!screener.scanning && !screener.error && filteredAndSortedMatches.length === 0 && (
        <div className="status">
          No golden stocks match. Adjust core scanning parameters and run a scan.
        </div>
      )}

      <div className="golden-stock-list">
        {filteredAndSortedMatches.map((stock) => (
          <GoldenStockRow key={stock.symbol} stock={stock} lastScannedAt={screener.lastScannedAt} />
        ))}
      </div>
    </div>
  );
}
