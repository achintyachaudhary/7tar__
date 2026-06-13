import { useMemo } from "react";
import LazyDbChart from "../components/LazyDbChart";
import GenericFiltersPanel from "../components/GenericFiltersPanel";
import ScanPageToolbar from "../components/ScanPageToolbar";
import ScanActivitySection from "../components/ScanActivitySection";
import ScanCriteriaPanel from "../components/ScanCriteriaPanel";
import ActiveFiltersSummary from "../components/ActiveFiltersSummary";
import SymbolLink from "../components/SymbolLink";
import ScanCardFooter from "../components/ScanCardFooter";
import {
  applyVolumeSurgeFilters,
  VOLUME_SURGE_FILTER_SECTIONS,
  VOLUME_SURGE_SORT_OPTIONS,
} from "../config/volumeSurgePageConfig";
import { useScreenerPage } from "../hooks/useScreenerPage";
import { useSortState } from "../hooks/useSortState";
import { fetchVolumeSurgeScanResults } from "../api";
import { getChartColors } from "../lib/chartTheme";
import type { VolumeSurgeMatch } from "../types/volumeSurge";

export default function VolumeSurgePage() {
  const screener = useScreenerPage<VolumeSurgeMatch>({
    scanType: "volume_surge",
    filterSections: VOLUME_SURGE_FILTER_SECTIONS,
    applyFilters: applyVolumeSurgeFilters,
    fetchCached: fetchVolumeSurgeScanResults,
  });

  const sort = useSortState(VOLUME_SURGE_SORT_OPTIONS, {
    defaultId: "volume_multiple",
    multiSort: true,
  });

  const filteredAndSortedMatches = useMemo(() => {
    return sort.applyTo(screener.filteredMatches);
  }, [screener.filteredMatches, sort.applyTo]);

  const progressPercent =
    screener.total > 0 ? Math.round((screener.scanned / screener.total) * 100) : 0;

  return (
    <div className="page-container volume-surge-page">
      <div className="page-header">
        <h1>Volume Surge Scanner</h1>
        <p className="page-subtitle">
          Unusual accumulation: several times normal volume with a strong up close — the
          institutional footprint. Watch for follow-through above the surge-day high; stop
          under the surge-day low.
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
        onRunScan={screener.handleRunScan}
        onCancelScan={screener.cancelScan}
        sortOptions={VOLUME_SURGE_SORT_OPTIONS}
        sortStack={sort.stack}
        onSortToggle={sort.toggle}
        onClearSecondarySort={sort.clearSecondary}
        multiSort
      />

      {screener.showFilters && (
        <GenericFiltersPanel
          sections={VOLUME_SURGE_FILTER_SECTIONS}
          values={screener.cosmeticFilters}
          onChange={screener.setCosmeticFilters}
          onReset={screener.resetCosmeticFilters}
          disabled={screener.scanning}
        />
      )}

      <ActiveFiltersSummary
        sections={VOLUME_SURGE_FILTER_SECTIONS}
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
        logTitle="Volume Surge scan log"
      />

      <div className="result-summary-bar">
        <div className="meta" style={{ fontSize: "1rem" }}>
          Found{" "}
          <strong style={{ color: "var(--accent)" }}>{filteredAndSortedMatches.length}</strong>{" "}
          accumulation candidates
          {filteredAndSortedMatches.length !== screener.matches.length && (
            <span style={{ color: "var(--muted)" }}>
              {" "}
              (of {screener.matches.length} total from scan)
            </span>
          )}
        </div>
      </div>

      {filteredAndSortedMatches.length > 0 ? (
        <div className="result-grid">
          {filteredAndSortedMatches.map((stock) => {
            const colors = getChartColors();
            return (
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
                    <span
                      className="result-card-sub"
                      style={{ color: stock.day_change_pct >= 0 ? "var(--green)" : "var(--red)" }}
                    >
                      {stock.day_change_pct >= 0 ? "+" : ""}
                      {stock.day_change_pct}% on surge day
                    </span>
                  </div>
                </div>

                <div className="result-tags">
                  <span className="result-tag result-tag-pos">
                    {stock.volume_multiple}× volume
                  </span>
                  <span className="result-tag">
                    Close {stock.close_strength_pct}% of range
                  </span>
                  <span className="result-tag result-tag-pos">
                    Entry &gt; ₹{stock.entry_price}
                  </span>
                  <span className="result-tag result-tag-neg">
                    Stop ₹{stock.stop_price}
                  </span>
                </div>

                <div style={{ height: "220px", position: "relative", width: "100%" }}>
                  <LazyDbChart
                    symbol={stock.symbol}
                    interval="1d"
                    height={220}
                    showVolume
                    priceLines={[
                      { price: stock.entry_price, color: colors.up, title: "Entry (surge high)" },
                      { price: stock.stop_price, color: colors.down, title: "Stop (surge low)" },
                    ]}
                  />
                </div>

                <ScanCardFooter lastScannedAt={screener.lastScannedAt} />
              </div>
            );
          })}
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
