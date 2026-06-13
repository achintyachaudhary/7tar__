import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  fetchLiveTradingCandidates,
  fetchLiveTradingState,
  fetchLiveTradingSummary,
  fetchLiveTrades,
  manualExitLiveTrade,
  sendLiveTradingClientReport,
  setLiveTradingAnalysisOverride,
  setLiveTradingEntriesPaused,
  setPreviewStrategy,
} from "../api";
import type {
  LiveTrade,
  LiveTradeCandidate,
  LiveTradingState,
  StrategySummary,
} from "../types/liveTrading";
import { useAppSocket } from "../context/AppSocketContext";
import { freshQuote, useLiveTicks } from "../context/LiveTicksContext";

interface LiveTradeSSEContextValue {
  state: LiveTradingState | null;
  candidates: LiveTradeCandidate[];
  trades: LiveTrade[];
  summary: StrategySummary | null;
  loading: boolean;
  error: string | null;
  sseConnected: boolean;
  modeLoading: boolean;
  entriesPauseLoading: boolean;
  reportLoading: boolean;
  reportMessage: string | null;
  setAnalysisOverride: (enabled: boolean) => Promise<void>;
  setEntriesPaused: (paused: boolean) => Promise<void>;
  setPreviewStrategyKey: (strategyKey: string) => Promise<void>;
  exitTrade: (tradeId: number) => Promise<void>;
  reportToClients: () => Promise<void>;
  refreshFromBackend: () => Promise<void>;
}

const LiveTradeSSEContext = createContext<LiveTradeSSEContextValue | null>(null);

const round2 = (v: number) => Math.round(v * 100) / 100;

const PRESERVED_STATE_KEYS: (keyof LiveTradingState)[] = [
  "entries_paused",
  "starting_capital",
  "realized_pnl",
  "unrealized_pnl",
  "total_pnl",
  "total_pnl_pct",
  "portfolio_equity",
  "deployed",
  "holdings_invested",
  "holdings_current",
  "holdings_pnl",
  "holdings_pnl_pct",
  "today_pnl",
  "today_pnl_pct",
  "available_cash",
  "max_per_trade",
  "trade_budget",
  "open_positions",
  "max_positions",
  "preview_strategy",
  "strategy_key",
];

function mergeLiveTradingState(
  prev: LiveTradingState | null,
  next: LiveTradingState,
): LiveTradingState {
  if (!prev) return next;
  const merged: LiveTradingState = { ...prev, ...next };
  for (const key of PRESERVED_STATE_KEYS) {
    const nextVal = next[key];
    if (nextVal === undefined || nextVal === null) {
      const prevVal = prev[key];
      if (prevVal !== undefined) {
        Object.assign(merged, { [key]: prevVal });
      }
    }
  }
  return merged;
}

function getSseUrl(): string {
  return `${window.location.origin}/sse/live-trades`;
}

export function LiveTradeSSEProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<LiveTradingState | null>(null);
  const [candidates, setCandidates] = useState<LiveTradeCandidate[]>([]);
  const [trades, setTrades] = useState<LiveTrade[]>([]);
  const [summary, setSummary] = useState<StrategySummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sseConnected, setSseConnected] = useState(false);
  const [modeLoading, setModeLoading] = useState(false);
  const [entriesPauseLoading, setEntriesPauseLoading] = useState(false);
  const [reportLoading, setReportLoading] = useState(false);
  const [reportMessage, setReportMessage] = useState<string | null>(null);
  const { quotes: liveQuotes } = useLiveTicks();
  const mounted = useRef(true);
  const esRef = useRef<EventSource | null>(null);

  const { subscribe } = useAppSocket();

  const syncFromBackend = useCallback(async () => {
    try {
      const s = await fetchLiveTradingState();
      const preview = s.preview_strategy ?? "smart_swing";
      const [c, t, sum] = await Promise.all([
        fetchLiveTradingCandidates(),
        fetchLiveTrades("all", preview),
        fetchLiveTradingSummary(),
      ]);
      if (!mounted.current) return;
      setState(s);
      setCandidates(c.candidates);
      setTrades(t.trades);
      setSummary(sum);
      setError(null);
    } catch (err) {
      if (!mounted.current) return;
      setError(err instanceof Error ? err.message : "Failed to load live trading");
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, []);

  const refreshSummaryAndTrades = useCallback(async (preview?: string) => {
    const strategyKey = preview ?? state?.preview_strategy ?? "smart_swing";
    try {
      const [t, sum] = await Promise.all([
        fetchLiveTrades("all", strategyKey),
        fetchLiveTradingSummary(),
      ]);
      if (!mounted.current) return;
      setTrades(t.trades);
      setSummary(sum);
    } catch {
      /* ignore background refresh errors */
    }
  }, [state?.preview_strategy]);

  // Initial load from REST
  useEffect(() => {
    mounted.current = true;
    syncFromBackend();
    return () => { mounted.current = false; };
  }, [syncFromBackend]);

  // Keep mode in sync across the 9:15 open boundary (engine ticks every 30s)
  useEffect(() => {
    const id = window.setInterval(() => void syncFromBackend(), 30_000);
    return () => window.clearInterval(id);
  }, [syncFromBackend]);

  // Handle live trade events from WS hub (cross-process bridge)
  useEffect(() => {
    const unsubs: (() => void)[] = [];

    unsubs.push(subscribe("live-trading:state", (msg) => {
      if (mounted.current) {
        setState((prev) => mergeLiveTradingState(prev, msg as unknown as LiveTradingState));
      }
    }));

    unsubs.push(subscribe("live-trading:candidates", (msg) => {
      const cands = (msg as any).candidates;
      if (mounted.current && cands) setCandidates(cands);
    }));

    unsubs.push(subscribe("live-trading:trades", (msg) => {
      const tradeList = (msg as any).trades;
      if (mounted.current && tradeList) {
        setTrades(tradeList);
      }
    }));

    unsubs.push(subscribe("live-trading:trade_opened", (msg) => {
      const trade = msg as unknown as LiveTrade;
      if (mounted.current && trade?.id) {
        setTrades((prev) => {
          if (prev.some((t) => t.id === trade.id)) return prev;
          return [...prev, trade];
        });
        void refreshSummaryAndTrades();
      }
    }));

    unsubs.push(subscribe("live-trading:trade_closed", (msg) => {
      const trade = msg as unknown as LiveTrade;
      if (mounted.current && trade?.id) {
        setTrades((prev) => prev.map((t) => (t.id === trade.id ? trade : t)));
        void refreshSummaryAndTrades();
      }
    }));

    return () => unsubs.forEach((u) => u());
  }, [subscribe, refreshSummaryAndTrades]);

  // SSE connection (kept as secondary transport)
  useEffect(() => {
    let reconnectTimer: ReturnType<typeof setTimeout>;

    function connectSSE() {
      const es = new EventSource(getSseUrl());
      esRef.current = es;

      es.onopen = () => setSseConnected(true);

      es.addEventListener("state", (e) => {
        try {
          const data = JSON.parse((e as MessageEvent).data);
          if (mounted.current) {
            setState((prev) => mergeLiveTradingState(prev, data as LiveTradingState));
          }
        } catch { /* ignore */ }
      });

      es.addEventListener("candidates", (e) => {
        try {
          const data = JSON.parse((e as MessageEvent).data);
          if (mounted.current) setCandidates(data.candidates ?? []);
        } catch { /* ignore */ }
      });

      es.addEventListener("trades", (e) => {
        try {
          const data = JSON.parse((e as MessageEvent).data);
          if (mounted.current && data.trades) {
            setTrades(data.trades);
          }
        } catch { /* ignore */ }
      });

      es.addEventListener("trade_opened", (e) => {
        try {
          const trade = JSON.parse((e as MessageEvent).data) as LiveTrade;
          if (mounted.current) {
            setTrades((prev) => {
              if (prev.some((t) => t.id === trade.id)) return prev;
              return [...prev, trade];
            });
            void refreshSummaryAndTrades();
          }
        } catch { /* ignore */ }
      });

      es.addEventListener("trade_closed", (e) => {
        try {
          const trade = JSON.parse((e as MessageEvent).data) as LiveTrade;
          if (mounted.current) {
            setTrades((prev) =>
              prev.map((t) => (t.id === trade.id ? trade : t)),
            );
            void refreshSummaryAndTrades();
          }
        } catch { /* ignore */ }
      });

      es.onerror = () => {
        setSseConnected(false);
        es.close();
        esRef.current = null;
        reconnectTimer = setTimeout(connectSSE, 5000);
      };
    }

    connectSSE();

    return () => {
      clearTimeout(reconnectTimer);
      esRef.current?.close();
      esRef.current = null;
    };
  }, [refreshSummaryAndTrades]);

  const setAnalysisOverride = useCallback(
    async (enabled: boolean) => {
      setModeLoading(true);
      try {
        const s = await setLiveTradingAnalysisOverride(enabled);
        if (mounted.current) setState(s);
        await syncFromBackend();
      } catch (err) {
        if (mounted.current) {
          setError(err instanceof Error ? err.message : "Mode change failed");
        }
      } finally {
        if (mounted.current) setModeLoading(false);
      }
    },
    [syncFromBackend],
  );

  const setEntriesPaused = useCallback(
    async (paused: boolean) => {
      setEntriesPauseLoading(true);
      try {
        const s = await setLiveTradingEntriesPaused(paused);
        if (mounted.current) setState((prev) => mergeLiveTradingState(prev, s));
      } catch (err) {
        if (mounted.current) {
          setError(err instanceof Error ? err.message : "Failed to update entry pause");
        }
      } finally {
        if (mounted.current) setEntriesPauseLoading(false);
      }
    },
    [],
  );

  const exitTrade = useCallback(
    async (tradeId: number) => {
      try {
        const result = await manualExitLiveTrade(tradeId);
        if (!mounted.current) return;
        if (result.trade) {
          setTrades((prev) =>
            prev.map((t) => (t.id === result.trade.id ? result.trade : t)),
          );
        }
        await syncFromBackend();
      } catch (err) {
        if (mounted.current) {
          setError(err instanceof Error ? err.message : "Manual exit failed");
        }
        throw err;
      }
    },
    [syncFromBackend],
  );

  const setPreviewStrategyKey = useCallback(
    async (strategyKey: string) => {
      try {
        const s = await setPreviewStrategy(strategyKey);
        if (mounted.current) {
          setState((prev) => mergeLiveTradingState(prev, s));
        }
        await syncFromBackend();
      } catch (err) {
        if (mounted.current) {
          setError(err instanceof Error ? err.message : "Failed to set preview strategy");
        }
        throw err;
      }
    },
    [syncFromBackend],
  );

  const reportToClients = useCallback(async () => {
    setReportLoading(true);
    setReportMessage(null);
    try {
      const result = await sendLiveTradingClientReport();
      if (mounted.current) {
        setReportMessage(result.message);
        if (!result.sent) setError(result.message);
      }
    } catch (err) {
      if (mounted.current) {
        const msg = err instanceof Error ? err.message : "Report failed";
        setReportMessage(msg);
        setError(msg);
      }
    } finally {
      if (mounted.current) setReportLoading(false);
    }
  }, []);

  // ── Live re-valuation ─────────────────────────────────────────────────────
  // Engine data is the baseline (it persists every ~30s); streamed quotes
  // overlay it per render, so a fresh engine push simply becomes the new base.

  const liveTrades = useMemo(() => {
    if (Object.keys(liveQuotes).length === 0) return trades;
    return trades.map((t) => {
      if (t.status !== "open") return t;
      const q = freshQuote(liveQuotes, t.symbol);
      if (!q || q.price === t.last_price) return t;
      return { ...t, last_price: q.price, updated_at: new Date(q.ts).toISOString() };
    });
  }, [trades, liveQuotes]);

  const liveCandidates = useMemo(() => {
    if (Object.keys(liveQuotes).length === 0) return candidates;
    return candidates.map((c) => {
      if (c.status === "closed" || c.status === "skipped") return c;
      const q = freshQuote(liveQuotes, c.symbol);
      if (!q || q.price === c.last_price) return c;
      return { ...c, last_price: q.price };
    });
  }, [candidates, liveQuotes]);

  const liveSummary = useMemo(() => {
    if (!summary || Object.keys(liveQuotes).length === 0) return summary;
    let changed = false;
    const strategies = summary.strategies.map((row) => {
      const open = row.open_trades ?? [];
      if (open.length === 0) return row;
      let delta = 0;
      for (const t of open) {
        const q = freshQuote(liveQuotes, t.symbol);
        if (!q) continue;
        delta += t.qty * (q.price - (t.last_price ?? t.entry_price));
      }
      if (delta === 0) return row;
      changed = true;
      const totalPnlAbs = round2(row.total_pnl_abs + delta);
      const invested = row.total_invested ?? 0;
      return {
        ...row,
        total_pnl_abs: totalPnlAbs,
        total_pct: invested > 0 ? round2((totalPnlAbs / invested) * 100) : row.total_pct,
      };
    });
    return changed ? { ...summary, strategies } : summary;
  }, [summary, liveQuotes]);

  const liveState = useMemo(() => {
    if (!state || Object.keys(liveQuotes).length === 0) return state;
    let delta = 0;
    for (const t of trades) {
      if (t.status !== "open") continue;
      const q = freshQuote(liveQuotes, t.symbol);
      if (!q) continue;
      delta += t.qty * (q.price - (t.last_price ?? t.entry_price));
    }
    if (delta === 0) return state;
    const patched = { ...state };
    const bump = (key: keyof LiveTradingState) => {
      const base = state[key];
      if (typeof base === "number") Object.assign(patched, { [key]: round2(base + delta) });
    };
    bump("unrealized_pnl");
    bump("total_pnl");
    bump("portfolio_equity");
    bump("holdings_current");
    bump("holdings_pnl");
    bump("today_pnl");
    if (typeof patched.total_pnl === "number" && state.starting_capital > 0) {
      patched.total_pnl_pct = round2((patched.total_pnl / state.starting_capital) * 100);
    }
    if (
      typeof patched.holdings_pnl === "number" &&
      typeof state.holdings_invested === "number" &&
      state.holdings_invested > 0
    ) {
      patched.holdings_pnl_pct = round2((patched.holdings_pnl / state.holdings_invested) * 100);
    }
    if (typeof patched.today_pnl === "number" && state.starting_capital > 0) {
      patched.today_pnl_pct = round2((patched.today_pnl / state.starting_capital) * 100);
    }
    return patched;
  }, [state, trades, liveQuotes]);

  const value = useMemo<LiveTradeSSEContextValue>(
    () => ({
      state: liveState,
      candidates: liveCandidates,
      trades: liveTrades,
      summary: liveSummary,
      loading,
      error,
      sseConnected,
      modeLoading,
      entriesPauseLoading,
      reportLoading,
      reportMessage,
      setAnalysisOverride,
      setEntriesPaused,
      setPreviewStrategyKey,
      exitTrade,
      reportToClients,
      refreshFromBackend: syncFromBackend,
    }),
    [
      liveState,
      liveCandidates,
      liveTrades,
      liveSummary,
      loading,
      error,
      sseConnected,
      modeLoading,
      entriesPauseLoading,
      reportLoading,
      reportMessage,
      setAnalysisOverride,
      setEntriesPaused,
      setPreviewStrategyKey,
      exitTrade,
      reportToClients,
      syncFromBackend,
    ],
  );

  return (
    <LiveTradeSSEContext.Provider value={value}>
      {children}
    </LiveTradeSSEContext.Provider>
  );
}

export function useLiveTradeSSE(): LiveTradeSSEContextValue {
  const ctx = useContext(LiveTradeSSEContext);
  if (!ctx) {
    throw new Error("useLiveTradeSSE must be used within LiveTradeSSEProvider");
  }
  return ctx;
}
