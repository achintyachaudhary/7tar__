import { useMemo } from "react";
import LazyDbChart from "../components/LazyDbChart";
import GenericFiltersPanel from "../components/GenericFiltersPanel";
import ScanPageToolbar from "../components/ScanPageToolbar";
import ScanActivitySection from "../components/ScanActivitySection";
import ScanCriteriaPanel from "../components/ScanCriteriaPanel";
import VolumeBadge from "../components/VolumeBadge";
import SymbolLink from "../components/SymbolLink";
import ScanCardFooter from "../components/ScanCardFooter";
import { formatISTDateOnly } from "../lib/formatTime";
import { getChartColors } from "../lib/chartTheme";
import { useScreenerPage } from "../hooks/useScreenerPage";
import { useSortState } from "../hooks/useSortState";
import { fetchDarvasScanResults } from "../api";
import type { DarvasMatch } from "../types/darvas";
import ActiveFiltersSummary from "../components/ActiveFiltersSummary";
import {
  applyDarvasFilters,
  DARVAS_FILTER_SECTIONS,
  DARVAS_SORT_OPTIONS,
} from "../config/darvasPageConfig";

export default function DarvasBoxPage() {
  const screener = useScreenerPage<DarvasMatch>({
    scanType: "darvas",
    filterSections: DARVAS_FILTER_SECTIONS,
    applyFilters: applyDarvasFilters,
    fetchCached: fetchDarvasScanResults,
  });

  const sort = useSortState(DARVAS_SORT_OPTIONS, { defaultId: "breakout", multiSort: true });

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
        <h1>Darvas Box Scanner</h1>
        <p className="page-subtitle">
          Identifies stocks breaking out above Darvas Box formations with volume confirmation.
          Box forms when price makes a new high, consolidates, then breaks out.
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
        sortOptions={DARVAS_SORT_OPTIONS}
        sortStack={sort.stack}
        onSortToggle={sort.toggle}
        onClearSecondarySort={sort.clearSecondary}
        multiSort
      />

      {screener.showFilters && (
        <GenericFiltersPanel
          sections={DARVAS_FILTER_SECTIONS}
          values={screener.cosmeticFilters}
          onChange={screener.setCosmeticFilters}
          onReset={screener.resetCosmeticFilters}
          disabled={screener.scanning}
        />
      )}

      <ActiveFiltersSummary
        sections={DARVAS_FILTER_SECTIONS}
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
        logTitle="Darvas Box scan log"
      />

      <div style={{ marginBottom: "1rem", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div className="meta" style={{ fontSize: "1rem" }}>
          Found <strong style={{ color: "var(--accent)" }}>{filteredAndSortedMatches.length}</strong>{" "}
          Darvas Box breakouts
          {filteredAndSortedMatches.length !== screener.matches.length && (
            <span style={{ color: "var(--muted)" }}> (of {screener.matches.length} total from scan)</span>
          )}
        </div>
      </div>

      {filteredAndSortedMatches.length > 0 ? (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(480px, 1fr))",
            gap: "1.25rem",
            marginBottom: "2rem",
          }}
        >
          {filteredAndSortedMatches.map((stock) => {
            const latestBox = stock.boxes.length > 0 ? stock.boxes[stock.boxes.length - 1] : null;
            const chartColors = getChartColors();
            const priceLines = [];
            if (latestBox) {
              priceLines.push({ price: latestBox.top, color: chartColors.down, title: "Box Top" });
              priceLines.push({ price: latestBox.bottom, color: chartColors.accent, title: "Box Bottom" });
            }

            return (
              <div
                key={stock.symbol}
                style={{
                  background: "var(--header-bg)",
                  border: "1px solid var(--border)",
                  borderRadius: "10px",
                  padding: "1.25rem",
                  boxShadow: "var(--shadow)",
                  display: "flex",
                  flexDirection: "column",
                  gap: "1rem",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                  <div>
                    <h3 style={{ margin: 0, fontSize: "1.2rem", fontWeight: 700, color: "var(--text)" }}>
                      <SymbolLink symbol={stock.symbol} />
                    </h3>
                    <span style={{ fontSize: "0.85rem", color: "var(--muted)" }}>{stock.company_name}</span>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div style={{ fontSize: "1.2rem", fontWeight: 700, color: "var(--accent)" }}>
                      ₹{stock.price}
                    </div>
                    <span style={{ fontSize: "0.85rem", color: "var(--green)", fontWeight: 600 }}>
                      +{stock.breakout_pct}% above box
                    </span>
                  </div>
                </div>

                <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                  <span
                    style={{
                      background: "rgba(139, 92, 246, 0.1)",
                      color: "#8b5cf6",
                      padding: "0.25rem 0.5rem",
                      borderRadius: "4px",
                      fontSize: "0.75rem",
                      fontWeight: 600,
                    }}
                  >
                    Darvas Box Breakout
                  </span>
                  <span
                    style={{
                      background: "color-mix(in srgb, var(--red) 8%, transparent)",
                      color: "var(--red)",
                      padding: "0.25rem 0.5rem",
                      borderRadius: "4px",
                      fontSize: "0.75rem",
                      fontWeight: 600,
                    }}
                  >
                    Box Top: ₹{stock.box_top}
                  </span>
                  <span
                    style={{
                      background: "rgba(59, 130, 246, 0.08)",
                      color: "#3b82f6",
                      padding: "0.25rem 0.5rem",
                      borderRadius: "4px",
                      fontSize: "0.75rem",
                      fontWeight: 600,
                    }}
                  >
                    Box Bottom: ₹{stock.box_bottom}
                  </span>
                  <span
                    style={{
                      background: "rgba(0,0,0,0.05)",
                      color: "var(--text)",
                      padding: "0.25rem 0.5rem",
                      borderRadius: "4px",
                      fontSize: "0.75rem",
                      fontWeight: 500,
                    }}
                  >
                    Range: {stock.box_range_pct}%
                  </span>
                  <VolumeBadge match={stock} />
                </div>

                {stock.boxes_count > 1 && (
                  <div style={{ fontSize: "0.85rem", color: "var(--muted)" }}>
                    {stock.boxes_count} Darvas boxes found in the last 6 months
                  </div>
                )}

                <div style={{ height: "220px", position: "relative", width: "100%" }}>
                  <LazyDbChart
                    symbol={stock.symbol}
                    interval="1d"
                    height={220}
                    priceLines={priceLines}
                  />
                </div>

                <ScanCardFooter
                  lastScannedAt={screener.lastScannedAt}
                  extra={
                    latestBox ? (
                      <span className="timestamp-label">
                        Box: {formatISTDateOnly(latestBox.start_date)} –{" "}
                        {formatISTDateOnly(latestBox.end_date)}
                      </span>
                    ) : undefined
                  }
                />
              </div>
            );
          })}
        </div>
      ) : (
        !screener.scanning && (
          <div className="status">
            No Darvas Box breakouts found. Adjust filters or run a new scan.
          </div>
        )
      )}
    </div>
  );
}
