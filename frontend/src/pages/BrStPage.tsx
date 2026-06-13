import { useMemo } from "react";
import LazyDbChart from "../components/LazyDbChart";
import GenericFiltersPanel from "../components/GenericFiltersPanel";
import ScanPageToolbar from "../components/ScanPageToolbar";
import ScanActivitySection from "../components/ScanActivitySection";
import ScanCriteriaPanel from "../components/ScanCriteriaPanel";
import ActiveFiltersSummary from "../components/ActiveFiltersSummary";
import VolumeBadge from "../components/VolumeBadge";
import SymbolLink from "../components/SymbolLink";
import ScanCardFooter from "../components/ScanCardFooter";
import {
  applyBreakoutFilters,
  BREAKOUT_FILTER_SECTIONS,
  BREAKOUT_SORT_OPTIONS,
} from "../config/breakoutPageConfig";
import { useScreenerPage } from "../hooks/useScreenerPage";
import { useSortState } from "../hooks/useSortState";
import { fetchBrStScanResults } from "../api";
import type { BrStMatch } from "../types/brst";

export default function BrStPage() {
  const screener = useScreenerPage<BrStMatch>({
    scanType: "brst",
    filterSections: BREAKOUT_FILTER_SECTIONS,
    applyFilters: applyBreakoutFilters,
    fetchCached: fetchBrStScanResults,
  });

  const sort = useSortState(BREAKOUT_SORT_OPTIONS, { defaultId: "tests", multiSort: true });

  const filteredAndSortedMatches = useMemo(() => {
    return sort.applyTo(screener.filteredMatches);
  }, [screener.filteredMatches, sort.applyTo]);

  const progressPercent =
    screener.total > 0 ? Math.round((screener.scanned / screener.total) * 100) : 0;

  const handleRefreshScan = () => {
    screener.handleRunScan();
  };

  return (
    <div className="page-container brst-page">
      <div className="page-header">
        <h1>Year Breakout Scanner</h1>
        <p className="page-subtitle">
          Daily chart analysis: stocks near the period high — either repeatedly tested resistance
          or trading at a fresh high with no overhead supply
        </p>
      </div>

      <ScanCriteriaPanel
        definition={screener.definition}
        scanParams={screener.scanParams}
        onScanParamsChange={screener.setScanParams}
        onResetParams={screener.resetScanParams}
        onSaveParams={screener.persistScanParams}
        disabled={screener.scanning}
      />

      <ScanPageToolbar
        showFilters={screener.showFilters}
        onToggleFilters={() => screener.setShowFilters((v) => !v)}
        scanning={screener.scanning}
        onRunScan={handleRefreshScan}
        onCancelScan={screener.cancelScan}
        sortOptions={BREAKOUT_SORT_OPTIONS}
        sortStack={sort.stack}
        onSortToggle={sort.toggle}
        onClearSecondarySort={sort.clearSecondary}
        multiSort
      />

      {screener.showFilters && (
        <GenericFiltersPanel
          sections={BREAKOUT_FILTER_SECTIONS}
          values={screener.cosmeticFilters}
          onChange={screener.setCosmeticFilters}
          onReset={screener.resetCosmeticFilters}
          disabled={screener.scanning}
        />
      )}

      <ActiveFiltersSummary
        sections={BREAKOUT_FILTER_SECTIONS}
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
        logTitle="Year Breakout scan log"
      />

      <div className="result-summary-bar">
        <div className="meta" style={{ fontSize: "1rem" }}>
          Found <strong style={{ color: "var(--accent)" }}>{filteredAndSortedMatches.length}</strong>{" "}
          matching breakout candidates
          {filteredAndSortedMatches.length !== screener.matches.length && (
            <span style={{ color: "var(--muted)" }}> (of {screener.matches.length} total from scan)</span>
          )}
        </div>
      </div>

      {filteredAndSortedMatches.length > 0 ? (
        <div className="result-grid">
          {filteredAndSortedMatches.map((stock) => (
            <div key={stock.symbol} className="result-card">
              <div className="result-card-head">
                <div>
                  <h3 className="result-card-title">
                    <SymbolLink symbol={stock.symbol} />
                  </h3>
                  <span className="result-card-name">{stock.company_name}</span>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div className="result-card-price">₹{stock.price}</div>
                  <span className="result-card-sub">
                    Distance: {stock.distance_pct}% from high
                  </span>
                </div>
              </div>

              <div className="result-tags">
                <span className="result-tag result-tag-pos">
                  ✓ Tested {stock.tests_count} times
                </span>
                <span className="result-tag result-tag-neg">
                  Resistance: ₹{stock.highest_high}
                </span>
                <VolumeBadge match={stock} />
                <span className="result-tag">Daily Interval</span>
              </div>

              <div style={{ height: "220px", position: "relative", width: "100%" }}>
                <LazyDbChart
                  symbol={stock.symbol}
                  interval="1d"
                  height={220}
                  markers={(stock.test_points ?? []).map((tp) => ({
                    time: tp.time,
                    position: "aboveBar" as const,
                    color: "#f59e0b",
                    shape: "arrowDown" as const,
                    text: `Test: ₹${tp.price}`,
                  }))}
                />
              </div>

              <ScanCardFooter lastScannedAt={screener.lastScannedAt} />
            </div>
          ))}
        </div>
      ) : (
        !screener.scanning && (
          <div className="status">
            No stocks matched the criteria. Adjust filters or run a new scan.
          </div>
        )
      )}

    </div>
  );
}
