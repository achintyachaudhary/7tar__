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
  applyVolSqueezeFilters,
  VOL_SQUEEZE_FILTER_SECTIONS,
  VOL_SQUEEZE_SORT_OPTIONS,
} from "../config/volSqueezePageConfig";
import { useScreenerPage } from "../hooks/useScreenerPage";
import { useSortState } from "../hooks/useSortState";
import { fetchVolSqueezeScanResults } from "../api";
import { getChartColors } from "../lib/chartTheme";
import type { VolSqueezeMatch } from "../types/volSqueeze";

export default function VolSqueezePage() {
  const screener = useScreenerPage<VolSqueezeMatch>({
    scanType: "vol_squeeze",
    filterSections: VOL_SQUEEZE_FILTER_SECTIONS,
    applyFilters: applyVolSqueezeFilters,
    fetchCached: fetchVolSqueezeScanResults,
  });

  const sort = useSortState(VOL_SQUEEZE_SORT_OPTIONS, {
    defaultId: "atr_ratio",
    multiSort: true,
  });

  const filteredAndSortedMatches = useMemo(() => {
    return sort.applyTo(screener.filteredMatches);
  }, [screener.filteredMatches, sort.applyTo]);

  const progressPercent =
    screener.total > 0 ? Math.round((screener.scanned / screener.total) * 100) : 0;

  const handleRefreshScan = () => {
    screener.handleRunScan();
  };

  return (
    <div className="page-container vol-squeeze-page">
      <div className="page-header">
        <h1>Volatility Squeeze Scanner</h1>
        <p className="page-subtitle">
          For sideways markets: tight ranges with contracting ATR and drying volume — coiled
          springs ahead of a range expansion. Entry on the range-high break, measured-move
          target, stop at the range low.
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
        sortOptions={VOL_SQUEEZE_SORT_OPTIONS}
        sortStack={sort.stack}
        onSortToggle={sort.toggle}
        onClearSecondarySort={sort.clearSecondary}
        multiSort
      />

      {screener.showFilters && (
        <GenericFiltersPanel
          sections={VOL_SQUEEZE_FILTER_SECTIONS}
          values={screener.cosmeticFilters}
          onChange={screener.setCosmeticFilters}
          onReset={screener.resetCosmeticFilters}
          disabled={screener.scanning}
        />
      )}

      <ActiveFiltersSummary
        sections={VOL_SQUEEZE_FILTER_SECTIONS}
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
        logTitle="Volatility Squeeze scan log"
      />

      <div className="result-summary-bar">
        <div className="meta" style={{ fontSize: "1rem" }}>
          Found{" "}
          <strong style={{ color: "var(--accent)" }}>{filteredAndSortedMatches.length}</strong>{" "}
          squeeze setups
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
                    <span className="result-card-sub">
                      {stock.range_pct}% range · {stock.range_days}d
                    </span>
                  </div>
                </div>

                <div className="result-tags">
                  <span className="result-tag result-tag-pos">
                    ATR {stock.atr_ratio}× of 1y avg
                  </span>
                  {stock.volume_dryup_ratio != null && (
                    <span className="result-tag">Vol {stock.volume_dryup_ratio}× 50d</span>
                  )}
                  <span className="result-tag">
                    Break ₹{stock.entry_price}
                  </span>
                  <span className="result-tag result-tag-pos">
                    Target ₹{stock.target_price}
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
                    priceLines={[
                      { price: stock.target_price, color: colors.up, title: "Target" },
                      { price: stock.range_high, color: colors.accent, title: "Range high (entry)" },
                      { price: stock.range_low, color: colors.down, title: "Range low (stop)" },
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
