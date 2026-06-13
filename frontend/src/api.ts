import type { ScanLogEntry } from "./types/scanLog";
import type { StockListsPayload } from "./types/stockLists";
import type { ChartResponse, ChartTimeframe } from "./types/chart";
import type {
  IpoBatchFetchResponse,
  IpoLlmResearchResponse,
  IpoLlmStatusResponse,
} from "./types/ipoResearch";
import type { IndicesResponse, IpoTrackResponse, ScanResponse, StockInsightsResponse } from "./types";

export async function fetchIndices(): Promise<IndicesResponse> {
  const res = await fetch("/api/indices");
  if (!res.ok) {
    throw new Error(`Failed to load indices (${res.status})`);
  }
  return res.json() as Promise<IndicesResponse>;
}

export async function fetchScan(
  minScore: number,
  index: string,
  refresh = false,
): Promise<ScanResponse> {
  const params = new URLSearchParams({
    min_score: String(minScore),
    limit: "100",
    index,
  });
  if (refresh) {
    params.set("refresh", "true");
  }

  const res = await fetch(`/api/scan?${params}`);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail =
      typeof body.detail === "string"
        ? body.detail
        : `Scan failed (${res.status})`;
    throw new Error(detail);
  }
  return res.json() as Promise<ScanResponse>;
}

export async function fetchIpoLlmStatus(
  symbols: string[],
): Promise<IpoLlmStatusResponse> {
  if (symbols.length === 0) {
    return { statuses: [] };
  }
  const params = new URLSearchParams({
    symbols: symbols.join(","),
  });
  const res = await fetch(`/api/ipo/llm-research/status?${params}`);
  if (!res.ok) {
    throw new Error(`IPO status failed (${res.status})`);
  }
  return res.json() as Promise<IpoLlmStatusResponse>;
}

export async function batchFetchIpoLlmResearch(
  items: { symbol: string; company_name?: string | null }[],
): Promise<IpoBatchFetchResponse> {
  const res = await fetch("/api/ipo/llm-research/batch", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      items: items.map((i) => ({
        symbol: i.symbol,
        company_name: i.company_name ?? null,
      })),
    }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail =
      typeof body.detail === "string"
        ? body.detail
        : `Batch IPO fetch failed (${res.status})`;
    throw new Error(detail);
  }
  return res.json() as Promise<IpoBatchFetchResponse>;
}

export async function fetchIpoLlmResearch(
  symbol: string,
): Promise<IpoLlmResearchResponse> {
  const encoded = encodeURIComponent(symbol);
  const res = await fetch(`/api/ipo/${encoded}/llm-research`);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail =
      typeof body.detail === "string"
        ? body.detail
        : `IPO research not found (${res.status})`;
    throw new Error(detail);
  }
  return res.json() as Promise<IpoLlmResearchResponse>;
}

export async function generateIpoLlmResearch(
  symbol: string,
  options?: { companyName?: string; refresh?: boolean },
): Promise<IpoLlmResearchResponse> {
  const encoded = encodeURIComponent(symbol);
  const params = new URLSearchParams();
  if (options?.companyName) {
    params.set("company_name", options.companyName);
  }
  if (options?.refresh) {
    params.set("refresh", "true");
  }
  const qs = params.toString();
  const res = await fetch(
    `/api/ipo/${encoded}/llm-research${qs ? `?${qs}` : ""}`,
    { method: "POST" },
  );
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail =
      typeof body.detail === "string"
        ? body.detail
        : `IPO LLM request failed (${res.status})`;
    throw new Error(detail);
  }
  return res.json() as Promise<IpoLlmResearchResponse>;
}

export async function fetchIpos(
  months: 1 | 2 | 6,
  refresh = false,
): Promise<IpoTrackResponse> {
  const params = new URLSearchParams({ months: String(months) });
  if (refresh) {
    params.set("refresh", "true");
  }

  const res = await fetch(`/api/ipo?${params}`);
  if (!res.ok) {
    throw new Error(`IPO fetch failed (${res.status})`);
  }
  return res.json() as Promise<IpoTrackResponse>;
}

export async function fetchStockChart(
  symbol: string,
  timeframe: ChartTimeframe,
): Promise<ChartResponse> {
  const encoded = encodeURIComponent(symbol);
  const res = await fetch(`/api/stock/${encoded}/chart?timeframe=${timeframe}`);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail =
      typeof body.detail === "string"
        ? body.detail
        : `Chart fetch failed (${res.status})`;
    throw new Error(detail);
  }
  return res.json() as Promise<ChartResponse>;
}

export async function fetchStockInsights(
  symbol: string,
): Promise<StockInsightsResponse> {
  const encoded = encodeURIComponent(symbol);
  const res = await fetch(`/api/stock/${encoded}/insights`);
  if (!res.ok) {
    throw new Error(`Insights failed (${res.status})`);
  }
  return res.json() as Promise<StockInsightsResponse>;
}

export async function refreshStockData(
  symbol: string,
): Promise<StockInsightsResponse> {
  const encoded = encodeURIComponent(symbol);
  const res = await fetch(`/api/refresh/stock/${encoded}`, { method: "POST" });
  if (!res.ok) {
    throw new Error(`Refresh failed (${res.status})`);
  }
  return res.json() as Promise<StockInsightsResponse>;
}

export interface WidgetItem {
  widget_type: string;
  size: "sm" | "md" | "lg";
  position: number;
  config: Record<string, unknown>;
}

export interface DashboardLayout {
  widgets: (WidgetItem & { id?: number })[];
}

export async function fetchDashboardLayout(): Promise<DashboardLayout> {
  const res = await fetch("/api/dashboard/layout");
  if (!res.ok) throw new Error(`Layout fetch failed (${res.status})`);
  return res.json() as Promise<DashboardLayout>;
}

export async function saveDashboardLayout(widgets: WidgetItem[]): Promise<void> {
  const res = await fetch("/api/dashboard/layout", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ widgets }),
  });
  if (!res.ok) throw new Error(`Layout save failed (${res.status})`);
}

export async function fetchIndexSummary() {
  const res = await fetch("/api/widgets/index-summary");
  if (!res.ok) throw new Error("Index summary failed");
  return res.json();
}

export async function fetchMarketIndices(refresh = false) {
  const params = refresh ? "?refresh=true" : "";
  const res = await fetch(`/api/market-indices${params}`);
  if (!res.ok) throw new Error(`Market indices failed (${res.status})`);
  return res.json();
}

export async function fetchMarketIndexChart(indexId: string) {
  const res = await fetch(`/api/market-indices/${encodeURIComponent(indexId)}/chart`);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail =
      typeof body.detail === "string"
        ? body.detail
        : `Index chart failed (${res.status})`;
    throw new Error(detail);
  }
  return res.json();
}

export async function fetchTopMovers() {
  const res = await fetch("/api/widgets/top-movers");
  if (!res.ok) throw new Error("Top movers failed");
  return res.json();
}

// ── IPO Research (ML) ───────────────────────────────────────────────────────

export async function fetchIpoPortfolioSimulation(months = 6, investmentInr = 100_000) {
  const params = new URLSearchParams({
    months: String(months),
    investment_inr: String(investmentInr),
  });
  const res = await fetch(`/api/ipo-research/portfolio-simulation?${params}`);
  if (!res.ok) throw new Error(`Portfolio simulation failed (${res.status})`);
  return res.json() as Promise<import("./types/ipoPortfolio").IpoPortfolioSimulation>;
}

export async function fetchIpoResearchDatasetStats(months = 6) {
  const params = new URLSearchParams({ months: String(months) });
  const res = await fetch(`/api/ipo-research/dataset/stats?${params}`);
  if (!res.ok) throw new Error(`Dataset stats failed (${res.status})`);
  return res.json();
}

export async function prepareIpoResearchDataset(force = false, months = 6) {
  const params = new URLSearchParams({
    batch_size: "40",
    months: String(months),
    subscription_batch_size: "8",
    fetch_subscription: "true",
  });
  if (force) params.set("force", "true");
  const res = await fetch(`/api/ipo-research/dataset/prepare?${params}`, {
    method: "POST",
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(
      typeof body.detail === "string" ? body.detail : `Prepare failed (${res.status})`,
    );
  }
  return res.json();
}

export async function fetchIpoResearchRuns() {
  const res = await fetch("/api/ipo-research/runs");
  if (!res.ok) throw new Error(`Runs list failed (${res.status})`);
  return res.json() as Promise<{ runs: import("./types/ipoResearchMl").IpoResearchRun[] }>;
}

export async function fetchIpoResearchRun(id: number) {
  const res = await fetch(`/api/ipo-research/runs/${id}`);
  if (!res.ok) throw new Error(`Run detail failed (${res.status})`);
  return res.json() as Promise<import("./types/ipoResearchMl").IpoResearchRun>;
}

export async function fetchIpoResearchAlgorithms() {
  const res = await fetch("/api/ipo-research/algorithms");
  if (!res.ok) throw new Error("Algorithms list failed");
  return res.json() as Promise<{
    algorithms: string[];
    targets: { id: string; label: string }[];
  }>;
}

export async function startIpoResearchRun(body: {
  algorithm: string;
  target: string;
  prepare_data?: boolean;
  force_data_refresh?: boolean;
}) {
  const res = await fetch("/api/ipo-research/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      algorithm: body.algorithm,
      target: body.target,
      prepare_data: body.prepare_data ?? false,
      force_data_refresh: body.force_data_refresh ?? false,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(
      typeof err.detail === "string" ? err.detail : `ML run failed (${res.status})`,
    );
  }
  return res.json() as Promise<import("./types/ipoResearchMl").IpoResearchRun>;
}

// ── Day Scan ──────────────────────────────────────────────────────────────────

export async function fetchDayScanTable() {
  const res = await fetch("/api/day-scan");
  if (!res.ok) throw new Error(`Day scan load failed (${res.status})`);
  return res.json() as Promise<import("./types/dayScan").DayScanListResponse>;
}

export async function fetchDayScanStatus() {
  const res = await fetch("/api/day-scan/status");
  if (!res.ok) throw new Error(`Day scan status failed (${res.status})`);
  return res.json() as Promise<import("./types/dayScan").DayScanStatus>;
}

export async function fetchDayScanSyncStatus() {
  const res = await fetch("/api/day-scan/sync-status");
  if (!res.ok) throw new Error(`Day scan sync status failed (${res.status})`);
  return res.json() as Promise<import("./types/dayScan").DayScanSyncStatus>;
}

export async function fetchListingFetchStatus() {
  const res = await fetch("/api/day-scan/listing-status");
  if (!res.ok) throw new Error(`Listing fetch status failed (${res.status})`);
  return res.json() as Promise<import("./types/dayScan").ListingFetchStatus>;
}

export async function startListingFetch() {
  const res = await fetch("/api/day-scan/fetch-from-listing", { method: "POST" });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(
      typeof body.message === "string" ? body.message : `Listing fetch failed (${res.status})`,
    );
  }
  return res.json();
}

export async function startDayScanFetch(force = false) {
  const params = force ? "?force=true" : "";
  const res = await fetch(`/api/day-scan/fetch${params}`, { method: "POST" });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(
      typeof body.message === "string" ? body.message : `Day scan fetch failed (${res.status})`,
    );
  }
  return res.json();
}

export async function startVolumeFetch(scope: "nifty50" | "all" = "nifty50") {
  const res = await fetch(`/api/day-scan/fetch-volume?scope=${scope}`, { method: "POST" });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(
      typeof body.message === "string" ? body.message : `Volume fetch failed (${res.status})`,
    );
  }
  return res.json();
}

export async function fetchScreeningRules() {
  const res = await fetch("/api/rules");
  if (!res.ok) throw new Error(`Rules load failed (${res.status})`);
  return res.json() as Promise<{ rules: import("./types/rules").ScreeningRule[] }>;
}

export type DayScanChartInterval = "1d" | "1wk" | "1mo";

export async function fetchDayScanChart(
  symbol: string,
  interval: DayScanChartInterval = "1d",
) {
  const encoded = encodeURIComponent(symbol);
  const res = await fetch(`/api/day-scan/${encoded}/chart?interval=${interval}`);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail =
      typeof body.detail === "string"
        ? body.detail
        : `Chart load failed (${res.status})`;
    throw new Error(detail);
  }
  return res.json() as Promise<import("./types/dayScan").DayScanChartResponse>;
}

// ── Database browser ─────────────────────────────────────────────────────────

export async function fetchDbTables() {
  const res = await fetch("/api/db/tables");
  if (!res.ok) throw new Error(`DB tables failed (${res.status})`);
  return res.json() as Promise<{ tables: import("./types/dayScan").DbTableMeta[] }>;
}

export async function fetchDbTableData(table: string, offset = 0, limit = 50) {
  const params = new URLSearchParams({
    offset: String(offset),
    limit: String(limit),
  });
  const res = await fetch(`/api/db/tables/${encodeURIComponent(table)}?${params}`);
  if (!res.ok) throw new Error(`DB table data failed (${res.status})`);
  return res.json() as Promise<import("./types/dayScan").DbTableData>;
}

// ── BrSt / Multi Year scan cache ─────────────────────────────────────────────

export async function fetchBrStScanResults() {
  const res = await fetch("/api/brst/scan-results");
  if (!res.ok) throw new Error(`BrSt scan results failed (${res.status})`);
  return res.json() as Promise<import("./types/scanCache").ScanCacheResponse>;
}

export async function fetchMultiYearScanResults() {
  const res = await fetch("/api/multi-year/scan-results");
  if (!res.ok) throw new Error(`Multi Year scan results failed (${res.status})`);
  return res.json() as Promise<import("./types/scanCache").ScanCacheResponse>;
}

export async function fetchGoldenScanResults(): Promise<{
  scan_type: string;
  matches: import("./types/golden").GoldenStockMatch[];
  filter: Record<string, unknown>;
  scanned: number;
  total: number;
  last_scanned_at: string | null;
}> {
  const res = await fetch("/api/golden-stocks/scan-results");
  if (!res.ok) throw new Error(`Golden scan results failed (${res.status})`);
  return res.json();
}

export async function fetchWeeklyScanResults(): Promise<{
  scan_type: string;
  matches: import("./types/weekly").WeeklyStockMatch[];
  filter: Record<string, unknown>;
  scanned: number;
  total: number;
  last_scanned_at: string | null;
}> {
  const res = await fetch("/api/weekly-stocks/scan-results");
  if (!res.ok) throw new Error(`Weekly scan results failed (${res.status})`);
  return res.json();
}

export async function fetchDarvasScanResults() {
  const res = await fetch("/api/darvas/scan-results");
  if (!res.ok) throw new Error(`Darvas scan results failed (${res.status})`);
  return res.json() as Promise<import("./types/scanCache").ScanCacheResponse>;
}

export async function fetchMeanReversionScanResults() {
  const res = await fetch("/api/mean-reversion/scan-results");
  if (!res.ok) throw new Error(`Mean Reversion scan results failed (${res.status})`);
  return res.json() as Promise<import("./types/scanCache").ScanCacheResponse>;
}

export async function fetchVolSqueezeScanResults() {
  const res = await fetch("/api/vol-squeeze/scan-results");
  if (!res.ok) throw new Error(`Volatility Squeeze scan results failed (${res.status})`);
  return res.json() as Promise<import("./types/scanCache").ScanCacheResponse>;
}

export async function fetchVolumeSurgeScanResults() {
  const res = await fetch("/api/volume-surge/scan-results");
  if (!res.ok) throw new Error(`Volume Surge scan results failed (${res.status})`);
  return res.json() as Promise<import("./types/scanCache").ScanCacheResponse>;
}

// ── IPO intel (scraped GMP + subscription) ───────────────────────────────────

export async function fetchIpoIntel() {
  const res = await fetch("/api/ipo-intel");
  if (!res.ok) throw new Error(`IPO intel fetch failed (${res.status})`);
  return res.json() as Promise<import("./types/ipoIntel").IpoIntelResponse>;
}

export async function refreshIpoIntel() {
  const res = await fetch("/api/ipo-intel/refresh", { method: "POST" });
  if (!res.ok) throw new Error(`IPO intel refresh failed (${res.status})`);
  return res.json() as Promise<import("./types/ipoIntel").IpoIntelJobStatus & { status: string }>;
}

export async function fetchIpoIntelStatus() {
  const res = await fetch("/api/ipo-intel/status");
  if (!res.ok) throw new Error(`IPO intel status failed (${res.status})`);
  return res.json() as Promise<import("./types/ipoIntel").IpoIntelJobStatus>;
}

// ── Vendors & news ───────────────────────────────────────────────────────────

export interface FeatureVendor {
  capability: string;
  label: string;
  description: string;
  vendor: string;
  vendor_label: string;
  vendor_kind: "api" | "scrape" | "lib";
  options: string[];
  env_override: string;
  degraded: boolean;
  note: string | null;
}

export async function fetchVendors(): Promise<{
  features: FeatureVendor[];
  upstox_configured: boolean;
}> {
  const res = await fetch("/api/vendors");
  if (!res.ok) throw new Error(`Vendors fetch failed (${res.status})`);
  return res.json();
}

export interface NewsArticle {
  symbol: string;
  heading: string | null;
  summary: string | null;
  thumbnail: string | null;
  article_link: string | null;
  published_time: number | null;
}

export async function fetchFollowingNews(refresh = false): Promise<{
  articles: NewsArticle[];
  symbols: string[];
  unresolved_symbols?: string[];
  vendor: string;
}> {
  const params = refresh ? "?refresh=true" : "";
  const res = await fetch(`/api/news/following${params}`);
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `News fetch failed (${res.status})`);
  }
  return res.json();
}

// ── User preferences (database: user_preferences table) ─────────────────────

export async function fetchUserPreferences(): Promise<Record<string, string>> {
  const res = await fetch("/api/preferences");
  if (!res.ok) throw new Error(`Preferences fetch failed (${res.status})`);
  const data = await res.json();
  return (data?.preferences ?? {}) as Record<string, string>;
}

export async function updateUserPreferences(
  preferences: Record<string, string>,
): Promise<void> {
  const res = await fetch("/api/preferences", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ preferences }),
  });
  if (!res.ok) throw new Error(`Preferences update failed (${res.status})`);
}

// ── Widget preferences ───────────────────────────────────────────────────────

export async function fetchWidgetPreferences(widgetId: string) {
  const res = await fetch(`/api/widget-preferences/${encodeURIComponent(widgetId)}`);
  if (!res.ok) throw new Error(`Widget preferences fetch failed (${res.status})`);
  return res.json() as Promise<import("./types/widgetPreferences").WidgetPreferences>;
}

export async function updateWidgetPreferences(
  widgetId: string,
  update: import("./types/widgetPreferences").WidgetPreferencesUpdate,
) {
  const res = await fetch(`/api/widget-preferences/${encodeURIComponent(widgetId)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(update),
  });
  if (!res.ok) throw new Error(`Widget preferences update failed (${res.status})`);
  return res.json();
}

// ── Live trading ─────────────────────────────────────────────────────────────

export async function fetchLiveTradingState() {
  const res = await fetch("/api/live-trading/state");
  if (!res.ok) throw new Error(`Live trading state failed (${res.status})`);
  return res.json() as Promise<import("./types/liveTrading").LiveTradingState>;
}

export async function setLiveTradingAnalysisOverride(analysisOverride: boolean) {
  const res = await fetch("/api/live-trading/mode", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ analysis_override: analysisOverride }),
  });
  if (!res.ok) throw new Error(`Live trading mode failed (${res.status})`);
  return res.json() as Promise<import("./types/liveTrading").LiveTradingState>;
}

export async function setLiveTradingEntriesPaused(entriesPaused: boolean) {
  const res = await fetch("/api/live-trading/entries-pause", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ entries_paused: entriesPaused }),
  });
  if (!res.ok) throw new Error(`Pause entries failed (${res.status})`);
  return res.json() as Promise<import("./types/liveTrading").LiveTradingState>;
}

export async function manualExitLiveTrade(tradeId: number) {
  const res = await fetch(`/api/live-trading/trades/${tradeId}/exit`, { method: "POST" });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = typeof body.message === "string" ? body.message : `Exit failed (${res.status})`;
    throw new Error(detail);
  }
  return body as Promise<{ status: string; trade: import("./types/liveTrading").LiveTrade; message: string }>;
}

export async function fetchLiveTradingCandidates() {
  const res = await fetch("/api/live-trading/candidates");
  if (!res.ok) throw new Error(`Live trading candidates failed (${res.status})`);
  return res.json() as Promise<{ candidates: import("./types/liveTrading").LiveTradeCandidate[] }>;
}

export async function fetchLiveTrades(
  status: "open" | "closed" | "all" = "all",
  strategy?: string,
) {
  const params = new URLSearchParams({ status });
  if (strategy) params.set("strategy", strategy);
  const res = await fetch(`/api/live-trading/trades?${params}`);
  if (!res.ok) throw new Error(`Live trades failed (${res.status})`);
  return res.json() as Promise<{ trades: import("./types/liveTrading").LiveTrade[] }>;
}

export async function setPreviewStrategy(strategyKey: string) {
  const res = await fetch("/api/live-trading/preview-strategy", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ strategy_key: strategyKey }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail =
      typeof body.message === "string" ? body.message : `Preview strategy failed (${res.status})`;
    throw new Error(detail);
  }
  return body as Promise<import("./types/liveTrading").LiveTradingState>;
}

export async function forceResetLiveTrading() {
  const res = await fetch("/api/live-trading/force-reset", { method: "POST" });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail =
      typeof body.message === "string" ? body.message : `Force reset failed (${res.status})`;
    throw new Error(detail);
  }
  return body as Promise<{
    status: string;
    message: string;
    state: import("./types/liveTrading").LiveTradingState;
  }>;
}

export async function fetchLiveTradingSummary() {
  const res = await fetch("/api/live-trading/summary");
  if (!res.ok) throw new Error(`Live trading summary failed (${res.status})`);
  return res.json() as Promise<import("./types/liveTrading").StrategySummary>;
}

export async function fetchStrategyTrades(strategyKey: string) {
  const res = await fetch(`/api/live-trading/strategy-trades?strategy=${encodeURIComponent(strategyKey)}`);
  if (!res.ok) throw new Error(`Strategy trades failed (${res.status})`);
  return res.json() as Promise<import("./types/liveTrading").StrategyTradesResponse>;
}

export async function sendLiveTradingClientReport() {
  const res = await fetch("/api/live-trading/report", { method: "POST" });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = typeof body.detail === "string" ? body.detail : `Report failed (${res.status})`;
    throw new Error(detail);
  }
  return res.json() as Promise<{ sent: boolean; message: string }>;
}

export async function fetchLiveTradingSyncPreview() {
  const res = await fetch("/api/live-trading/sync-preview");
  if (!res.ok) throw new Error(`Sync preview failed (${res.status})`);
  return res.json() as Promise<import("./types/liveTrading").SyncPreviewResponse>;
}

export async function syncLiveTradingScreeners(options?: {
  scanTypes?: string[];
  excluded?: { symbol: string; source: string }[];
}) {
  const res = await fetch("/api/live-trading/sync-screener", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      scan_types: options?.scanTypes ?? [],
      excluded: options?.excluded ?? [],
    }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = typeof body.detail === "string" ? body.detail : `Sync failed (${res.status})`;
    throw new Error(detail);
  }
  return res.json() as Promise<{
    status: string;
    synced_from: string[];
    candidates_added: number;
    candidates_removed?: number;
    message?: string;
  }>;
}

export async function removeLiveTradeCandidate(symbol: string, source: string) {
  const params = new URLSearchParams({ symbol, source });
  const res = await fetch(`/api/live-trading/candidates?${params}`, { method: "DELETE" });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = typeof body.message === "string" ? body.message : `Remove failed (${res.status})`;
    throw new Error(detail);
  }
  return res.json() as Promise<{ status: string; removed: boolean; message?: string }>;
}

// ── Schedules ─────────────────────────────────────────────────────────────────

export interface ScanSchedule {
  id: number;
  scan_type: string;
  enabled: boolean;
  frequency: string;
  time_of_day: string;
  timezone: string;
  created_at: string;
  updated_at: string;
}

export interface ScanHistoryEntry {
  id: number;
  scan_type: string;
  status: string;
  duration_sec: number | null;
  matched_count: number | null;
  total_scanned: number | null;
  error_message: string | null;
  triggered_by: string;
  created_at: string;
  skipped_count?: number;
  error_count?: number;
  matched_symbols?: string[];
}

export interface ScanHistoryDetail extends ScanHistoryEntry {
  details?: {
    total?: number;
    scanned?: number;
    matched_count?: number;
    skipped_count?: number;
    error_count?: number;
    matched_symbols?: string[];
    skipped_symbols?: string[];
    errors?: { symbol: string; error: string }[];
    scan_config?: Record<string, unknown>;
    duration_sec?: number;
    log_tail?: ScanLogEntry[];
  } | null;
}

export async function fetchScanSchedules(): Promise<ScanSchedule[]> {
  const res = await fetch("/api/schedules");
  if (!res.ok) throw new Error(`Failed to fetch schedules (${res.status})`);
  return res.json() as Promise<ScanSchedule[]>;
}

export async function updateScanSchedule(
  scanType: string,
  config: {
    enabled: boolean;
    frequency: string;
    time_of_day: string;
    timezone?: string;
  },
): Promise<ScanSchedule> {
  const res = await fetch(`/api/schedules/${scanType}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = typeof body.detail === "string" ? body.detail : `Update failed (${res.status})`;
    throw new Error(detail);
  }
  return res.json() as Promise<ScanSchedule>;
}

export async function fetchScanHistory(limit = 50): Promise<ScanHistoryEntry[]> {
  const res = await fetch(`/api/schedules/history/recent?limit=${limit}`);
  if (!res.ok) throw new Error(`Failed to fetch scan history (${res.status})`);
  return res.json() as Promise<ScanHistoryEntry[]>;
}

export async function fetchScanHistoryDetail(historyId: number): Promise<ScanHistoryDetail> {
  const res = await fetch(`/api/schedules/history/${historyId}`);
  if (!res.ok) throw new Error(`Failed to fetch scan history detail (${res.status})`);
  return res.json() as Promise<ScanHistoryDetail>;
}

// ── Stock lists (favorites / blacklist) ───────────────────────────────────────

export async function fetchStockLists(): Promise<StockListsPayload> {
  const res = await fetch("/api/stock-lists");
  if (!res.ok) throw new Error(`Failed to fetch stock lists (${res.status})`);
  return res.json() as Promise<StockListsPayload>;
}

export async function fetchStockListsTable(): Promise<{
  rows: import("./types/stockListTable").EnrichedStockListRow[];
  count: number;
}> {
  const res = await fetch("/api/stock-lists/table");
  if (!res.ok) throw new Error(`Failed to fetch stock list table (${res.status})`);
  return res.json();
}

export async function replaceStockLists(
  favorites: string[],
  blacklist: string[],
): Promise<StockListsPayload> {
  const res = await fetch("/api/stock-lists", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ favorites, blacklist }),
  });
  if (!res.ok) throw new Error(`Failed to save stock lists (${res.status})`);
  return res.json() as Promise<StockListsPayload>;
}

export async function addToStockList(
  listType: "favorite" | "fishy" | "blacklist" | "following",
  symbol: string,
): Promise<StockListsPayload> {
  const enc = encodeURIComponent(symbol);
  const res = await fetch(`/api/stock-lists/${listType}/${enc}`, { method: "POST" });
  if (!res.ok) throw new Error(`Failed to add to ${listType} (${res.status})`);
  return res.json() as Promise<StockListsPayload>;
}

export async function removeFromStockList(
  listType: "favorite" | "fishy" | "blacklist" | "following",
  symbol: string,
): Promise<StockListsPayload> {
  const enc = encodeURIComponent(symbol);
  const res = await fetch(`/api/stock-lists/${listType}/${enc}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`Failed to remove from ${listType} (${res.status})`);
  return res.json() as Promise<StockListsPayload>;
}

// ── Bulk Deals ────────────────────────────────────────────────────────────────

export interface BulkDeal {
  id: number;
  deal_date: string;
  symbol: string;
  security_name: string | null;
  client_name: string;
  buy_sell: string;
  quantity: number;
  trade_price: number;
  amount: number;
  market_cap_cr: number | null;
  remarks: string | null;
  change_1d_pct: number | null;
  fetched_at: string;
}

export interface BulkDealStockAnalytics {
  symbol: string;
  security_name: string | null;
  deal_count: number;
  total_buy_amount: number;
  total_sell_amount: number;
  deals: BulkDeal[];
}

export interface BulkDealClientAnalytics {
  client_name: string;
  deal_count: number;
  unique_stocks: number;
  total_buy_amount: number;
  total_sell_amount: number;
  total_volume: number;
  stocks: BulkDealStockAnalytics[];
}

export interface BulkDealsAnalyticsResponse {
  date: string | null;
  client_count: number;
  deal_count: number;
  clients: BulkDealClientAnalytics[];
}

export async function fetchBulkDeals(date?: string): Promise<BulkDeal[]> {
  const params = new URLSearchParams();
  if (date) params.set("date", date);
  params.set("limit", "500");
  const res = await fetch(`/api/bulk-deals?${params}`);
  if (!res.ok) throw new Error(`Failed to fetch bulk deals (${res.status})`);
  return res.json() as Promise<BulkDeal[]>;
}

export async function fetchBulkDealDates(): Promise<string[]> {
  const res = await fetch("/api/bulk-deals/dates");
  if (!res.ok) throw new Error(`Failed to fetch deal dates (${res.status})`);
  return res.json() as Promise<string[]>;
}

export async function fetchBulkDealsAnalytics(): Promise<BulkDealsAnalyticsResponse> {
  const res = await fetch("/api/bulk-deals/analytics");
  if (!res.ok) throw new Error(`Failed to fetch analytics (${res.status})`);
  return res.json() as Promise<BulkDealsAnalyticsResponse>;
}

export async function triggerBulkDealsFetch(): Promise<{
  status: string;
  count: number;
  total_fetched?: number;
  duration_sec: number;
}> {
  const res = await fetch("/api/bulk-deals/fetch", { method: "POST" });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = typeof body.detail === "string" ? body.detail : `Fetch failed (${res.status})`;
    throw new Error(detail);
  }
  return res.json();
}

// ── Index / Sector Rotation ───────────────────────────────────────────────────

export interface RotationSignal {
  index_name: string;
  ticker: string;
  last_close: number;
  rrg: {
    rs_ratio: number;
    rs_momentum: number;
    quadrant: string;
    direction: string;
    tail_ratio: (number | null)[];
    tail_momentum: (number | null)[];
    tail_dates: string[];
  };
  returns: Record<string, number | null>;
  relative_returns: Record<string, number | null>;
}

export interface SectorRotationData {
  status?: string;
  message?: string;
  _refreshing?: boolean;
  sectors?: RotationSignal[];
  benchmark_returns?: Record<string, number | null>;
  quadrant_summary?: Record<string, string[]>;
  rotation_narrative?: string[];
  failed_sectors?: string[];
  computed_at?: string;
  duration_sec?: number;
}

export async function fetchSectorRotation(): Promise<SectorRotationData> {
  const res = await fetch("/api/indices-analysis/rotation");
  if (!res.ok) throw new Error(`Failed to fetch rotation data (${res.status})`);
  return res.json();
}

export async function triggerRotationRefresh(): Promise<{ status: string }> {
  const res = await fetch("/api/indices-analysis/rotation/refresh", { method: "POST" });
  if (!res.ok) throw new Error(`Failed to trigger refresh (${res.status})`);
  return res.json();
}

export async function fetchIndexCategories(): Promise<Record<string, string[]>> {
  const res = await fetch("/api/indices-analysis/categories");
  if (!res.ok) throw new Error(`Failed to fetch categories (${res.status})`);
  return res.json();
}

export interface IndexChartBar {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
}

export interface IndexChartResponse {
  index_name: string;
  ticker?: string;
  period: string;
  bars: IndexChartBar[];
  error?: string;
}

export async function fetchIndexChart(
  indexName: string,
  period: string = "1y",
): Promise<IndexChartResponse> {
  const res = await fetch(`/api/indices-analysis/chart/${encodeURIComponent(indexName)}?period=${period}`);
  if (!res.ok) throw new Error(`Failed to fetch chart (${res.status})`);
  return res.json();
}

export async function fetchScanDefinition(scanType: string): Promise<
  import("./types/scanConfig").ScanDefinition
> {
  const res = await fetch(`/api/scan-config/definitions/${encodeURIComponent(scanType)}`);
  if (!res.ok) throw new Error(`Scan definition failed (${res.status})`);
  return res.json();
}

export async function fetchScanDefinitions(): Promise<{
  definitions: import("./types/scanConfig").ScanDefinition[];
}> {
  const res = await fetch("/api/scan-config/definitions");
  if (!res.ok) throw new Error(`Scan definitions failed (${res.status})`);
  return res.json();
}

export async function exportScanProfiles(): Promise<
  import("./types/scanConfig").ScanProfileBundle
> {
  const res = await fetch("/api/scan-config/export");
  if (!res.ok) throw new Error(`Export failed (${res.status})`);
  return res.json();
}

export async function importScanProfiles(bundle: unknown): Promise<{
  valid: boolean;
  errors: string[];
  profile_count: number;
  profiles: import("./types/scanConfig").ScanConfigV1[];
}> {
  const res = await fetch("/api/scan-config/import", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ bundle }),
  });
  if (!res.ok) throw new Error(`Import validation failed (${res.status})`);
  return res.json();
}

export async function saveScanParams(
  scanType: string,
  scanConfig: import("./types/scanConfig").ScanConfigV1,
): Promise<{ saved: boolean; scan_type: string }> {
  const res = await fetch(`/api/scan-config/${encodeURIComponent(scanType)}/params`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scan_config: scanConfig }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(
      typeof body.detail === "string" ? body.detail : `Save parameters failed (${res.status})`,
    );
  }
  return res.json();
}

export async function runScanProfile(
  scanConfig: import("./types/scanConfig").ScanConfigV1,
): Promise<{ started: boolean; scan_type: string }> {
  const res = await fetch("/api/scan-config/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scan_config: scanConfig }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(
      typeof body.detail === "string" ? body.detail : `Run profile failed (${res.status})`,
    );
  }
  return res.json();
}

export async function emailScanProfilesExport(): Promise<{ sent: boolean; profiles: number }> {
  const res = await fetch("/api/scan-config/email-export", { method: "POST" });
  if (!res.ok) throw new Error(`Email export failed (${res.status})`);
  return res.json();
}

export async function fetchStockSymbolSuggestions(
  query: string,
  limit = 12,
): Promise<{
  suggestions: {
    symbol: string;
    company_name: string;
    last_price: number | null;
  }[];
}> {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  const res = await fetch(`/api/alerts/symbol-search?${params}`);
  if (!res.ok) throw new Error(`Symbol search failed (${res.status})`);
  return res.json();
}

export async function fetchPriceAlerts(
  activeOnly = false,
  withMarket = true,
): Promise<{
  alerts: import("./types/alerts").PriceAlert[];
}> {
  const params = new URLSearchParams();
  if (activeOnly) params.set("active_only", "true");
  if (!withMarket) params.set("with_market", "false");
  const qs = params.toString();
  const res = await fetch(`/api/alerts${qs ? `?${qs}` : ""}`);
  if (!res.ok) throw new Error(`Failed to load alerts (${res.status})`);
  return res.json();
}

export async function createPriceAlert(payload: {
  symbol: string;
  target_price: number;
  direction: "above" | "below";
  company_name?: string;
  email?: string;
  note?: string;
}): Promise<{ alert: import("./types/alerts").PriceAlert }> {
  const res = await fetch("/api/alerts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(
      typeof body.detail === "string" ? body.detail : `Create alert failed (${res.status})`,
    );
  }
  return res.json();
}

export async function deletePriceAlert(alertId: number): Promise<void> {
  const res = await fetch(`/api/alerts/${alertId}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`Delete alert failed (${res.status})`);
}

// ---------------------------------------------------------------------------
// Stock AI (lm/ RAG service — proxied via /lm-api, see vite.config.ts)
// ---------------------------------------------------------------------------

export interface StockAiPriceSummary {
  last_close: number;
  last_date: string | null;
  return_1w_pct: number | null;
  return_1m_pct: number | null;
  return_3m_pct: number | null;
  return_1y_pct: number | null;
  high_52w: number;
  low_52w: number;
}

export interface StockAiNewsDoc {
  ticker?: string;
  title?: string;
  text?: string;
  source?: string;
  date?: string;
  score?: number;
}

export interface StockAiFinancialPeriod {
  period_label: string;
  revenue_cr: number | null;
  profit_cr: number | null;
  period_date: string | null;
}

export interface StockAiWebResult {
  title: string;
  url: string;
  content: string;
  engine?: string | null;
  published?: string | null;
}

export interface StockAiAnalysis {
  symbol: string;
  report: string;
  reasoning: string;
  web_used?: StockAiWebResult[];
  data: {
    profile: {
      company_name?: string | null;
      sector?: string | null;
      industry?: string | null;
      market_cap_cr?: number | null;
      cap_category?: string | null;
    } | null;
    snapshot: {
      company_name?: string | null;
      pe_ratio?: number | null;
      roce_pct?: number | null;
      market_cap_cr?: number | null;
    } | null;
    price_summary: StockAiPriceSummary | null;
    financials: {
      quarterly: StockAiFinancialPeriod[];
      yearly: StockAiFinancialPeriod[];
    };
    holdings: {
      promoter_pct?: number | null;
      fii_pct?: number | null;
      dii_pct?: number | null;
      public_pct?: number | null;
      as_of?: string | null;
    } | null;
  };
  prices: { trade_date: string; close: number | null }[];
  news_used: StockAiNewsDoc[];
}

export async function fetchStockAiAnalysis(
  symbol: string,
  question?: string,
  useWeb = false,
): Promise<StockAiAnalysis> {
  const res = await fetch("/lm-api/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ symbol, question: question || null, use_web: useWeb }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(
      typeof body.detail === "string" ? body.detail : `Stock AI analysis failed (${res.status})`,
    );
  }
  return res.json();
}

export interface SearxngStatus {
  url: string;
  available: boolean;
  json: boolean;
  reason?: string | null;
}

export async function fetchStockAiHealth(): Promise<{
  ollama: boolean;
  qdrant: boolean;
  database: string;
  model: string;
  searxng?: SearxngStatus;
}> {
  const res = await fetch("/lm-api/health");
  if (!res.ok) throw new Error(`Stock AI service unreachable (${res.status})`);
  return res.json();
}

export interface PulseNewsItem {
  title: string;
  link: string | null;
  source: string | null;
  snippet: string | null;
  summary: string | null;
  model: string | null;
  published_at: string | null;
  summarized_at: string | null;
}

export interface PulseRunInfo {
  started_at: string | null;
  finished_at: string | null;
  status: string | null;
  triggered_by: string | null;
  items_fetched: number;
  items_new: number;
  error: string | null;
}

export interface PulseNewsResponse {
  items: PulseNewsItem[];
  running: boolean;
  last_run: PulseRunInfo | null;
}

export async function fetchPulseNews(limit = 30): Promise<PulseNewsResponse> {
  const res = await fetch(`/lm-api/pulse/news?limit=${limit}`);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(
      typeof body.detail === "string" ? body.detail : `Pulse news failed (${res.status})`,
    );
  }
  return res.json();
}

export async function triggerPulseRefresh(): Promise<{ started: boolean; reason?: string }> {
  const res = await fetch("/lm-api/pulse/refresh", { method: "POST" });
  if (!res.ok) throw new Error(`Pulse refresh failed (${res.status})`);
  return res.json();
}

// ---------------------------------------------------------------------------
// Stock AI data inspection (Database page → Stock AI tab)
// ---------------------------------------------------------------------------

export interface LmTableInfo {
  name: string;
  row_count: number;
  managed_by: string;
}

export interface LmServerDatabase {
  name: string;
  size: string;
  active: boolean;
}

export interface LmInspectOverview {
  postgres: {
    available: boolean;
    reason?: string;
    source?: string;
    dialect?: string;
    host?: string | null;
    port?: number | null;
    active_database?: string | null;
    user?: string | null;
    dsn_masked?: string;
    server_databases?: LmServerDatabase[];
    lm_tables?: LmTableInfo[];
    screener_tables?: LmTableInfo[];
  };
  qdrant: {
    available: boolean;
    reason?: string;
    url: string;
    collection: string;
    points_count?: number;
    vector_size?: number | null;
    distance?: string;
  };
}

export interface LmVectorPoint {
  id: string;
  ticker: string | null;
  title: string | null;
  source: string | null;
  date: string | null;
  text: string | null;
  vector_dim: number | null;
  vector_preview: number[];
}

export interface LmVectorsResponse {
  collection: string;
  vector_size: number | null;
  distance: string;
  total: number;
  offset: number;
  limit: number;
  points: LmVectorPoint[];
}

export interface LmTableData {
  table: string;
  columns: string[];
  rows: Record<string, unknown>[];
  total: number;
  offset: number;
  limit: number;
}

export async function fetchLmInspectOverview(): Promise<LmInspectOverview> {
  const res = await fetch("/lm-api/inspect/overview");
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(
      typeof body.detail === "string" ? body.detail : `Stock AI inspect failed (${res.status})`,
    );
  }
  return res.json();
}

export async function fetchLmVectors(offset = 0, limit = 20): Promise<LmVectorsResponse> {
  const res = await fetch(`/lm-api/inspect/vectors?offset=${offset}&limit=${limit}`);
  if (!res.ok) throw new Error(`Vector data failed (${res.status})`);
  return res.json();
}

export async function fetchLmTable(table: string, offset = 0, limit = 50): Promise<LmTableData> {
  const res = await fetch(
    `/lm-api/inspect/pg-table/${encodeURIComponent(table)}?offset=${offset}&limit=${limit}`,
  );
  if (!res.ok) throw new Error(`Table read failed (${res.status})`);
  return res.json();
}
