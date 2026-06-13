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
import { fetchMultiYearScanResults } from "../api";
import type { MultiYearMatch, TestPoint } from "../types/multiYear";

export default function MultiYearBreakoutPage() {
  const screener = useScreenerPage<MultiYearMatch>({
    scanType: "multi_year",
    filterSections: BREAKOUT_FILTER_SECTIONS,
    applyFilters: applyBreakoutFilters,
    fetchCached: fetchMultiYearScanResults,
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
    <div className="page-container multi-year-page">
      <div className="page-header">
        <h1>Multi Year Breakout Scanner</h1>
        <p className="page-subtitle">
          3-year weekly chart analysis: high-testing resistance levels (within 3% from top, tested
          2+ times)
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
        logTitle="Multi-Year Breakout scan log"
      />

      <div style={{ marginBottom: "1rem", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div className="meta" style={{ fontSize: "1rem" }}>
          Found <strong style={{ color: "var(--accent)" }}>{filteredAndSortedMatches.length}</strong>{" "}
          stocks matching Multi Year Breakout criteria
          {filteredAndSortedMatches.length !== screener.matches.length && (
            <span style={{ color: "var(--muted)" }}> (of {screener.matches.length} total from scan)</span>
          )}
        </div>
      </div>

      {filteredAndSortedMatches.length === 0 && !screener.scanning && !screener.error && (
        <div className="status">
          No stocks match the criteria. Adjust filters or run a new scan.
        </div>
      )}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(500px, 1fr))",
          gap: "1.5rem",
          marginBottom: "2rem",
        }}
      >
        {filteredAndSortedMatches.map((stock) => (
          <div
            key={stock.symbol}
            style={{
              background: "var(--bg-card)",
              border: "1px solid var(--border)",
              borderRadius: "8px",
              padding: "1rem",
              boxShadow: "var(--shadow)",
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "flex-start",
                marginBottom: "0.75rem",
              }}
            >
              <div>
                <h3 style={{ margin: 0, fontSize: "1.125rem", fontWeight: 600 }}>
                  <SymbolLink symbol={stock.symbol} />
                </h3>
                <p style={{ margin: "0.25rem 0 0 0", fontSize: "0.85rem", color: "var(--muted)" }}>
                  {stock.company_name}
                </p>
              </div>
              <div style={{ textAlign: "right" }}>
                <div style={{ fontSize: "1.25rem", fontWeight: 600, color: "var(--accent)" }}>
                  ₹{stock.price.toFixed(2)}
                </div>
                <div
                  style={{
                    fontSize: "0.8rem",
                    color: stock.distance_pct < 1 ? "var(--success)" : "var(--warning)",
                  }}
                >
                  {stock.distance_pct.toFixed(2)}% from ATH
                </div>
              </div>
            </div>

            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: "0.5rem",
                marginBottom: "0.75rem",
              }}
            >
              <div style={{ padding: "0.5rem", background: "rgba(0,0,0,0.08)", borderRadius: "6px" }}>
                <div style={{ fontSize: "0.75rem", color: "var(--muted)", marginBottom: "0.25rem" }}>
                  Resistance Level
                </div>
                <div style={{ fontWeight: 600 }}>₹{stock.highest_high.toFixed(2)}</div>
              </div>
              <div style={{ padding: "0.5rem", background: "rgba(0,0,0,0.08)", borderRadius: "6px" }}>
                <div style={{ fontSize: "0.75rem", color: "var(--muted)", marginBottom: "0.25rem" }}>
                  Tests
                </div>
                <div style={{ fontWeight: 600, color: "var(--accent)" }}>{stock.tests_count}x</div>
              </div>
            </div>

            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginBottom: "0.25rem" }}>
              <VolumeBadge match={stock} />
            </div>

            <div style={{ height: "200px", marginTop: "0.75rem" }}>
              <LazyDbChart
                symbol={stock.symbol}
                interval="1wk"
                height={200}
                markers={(stock.test_points ?? []).map((tp: TestPoint) => ({
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

    </div>
  );
}
