import type { StrategySummaryRow } from "../../types/liveTrading";
import { useLiveTradeSSE } from "../../context/LiveTradeSSEContext";
import TimestampLabel from "../TimestampLabel";

function fmt(v: number, prefix = ""): string {
  const sign = v >= 0 ? "+" : "";
  return `${prefix}${sign}${v.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

function pctFmt(v: number): string {
  const sign = v >= 0 ? "+" : "";
  return `${sign}${v.toFixed(1)}%`;
}

function cls(v: number): string {
  return v > 0 ? "positive" : v < 0 ? "negative" : "";
}

function StrategyRow({ row }: { row: StrategySummaryRow }) {
  if (!row.executed) return null;

  return (
    <div className="strategy-summary-row">
      <div className="strategy-summary-name">{row.label}</div>
      <div className="strategy-summary-stats">
        <span title="Trades">{row.trades} trades</span>
        <span title="Win rate" className={cls(row.win_rate - 50)}>
          {row.win_rate.toFixed(0)}% win
        </span>
        <span title="Total P&L" className={`strategy-summary-pnl ${cls(row.total_pnl_abs)}`}>
          {fmt(row.total_pnl_abs, "₹")}
        </span>
        <span title="Total %" className={cls(row.total_pct)}>
          {pctFmt(row.total_pct)}
        </span>
      </div>
    </div>
  );
}

export default function StrategySummaryWidget() {
  // Shared live-trading context: engine baseline + ~3s streamed re-valuation.
  const { summary, state, loading } = useLiveTradeSSE();

  if (loading) return <p className="meta">Loading strategy summary...</p>;
  if (!summary || !state) return <p className="meta">No live trading data</p>;

  const executed = summary.strategies.filter((s) => s.executed);
  if (executed.length === 0)
    return <p className="meta">No strategies have been executed yet</p>;

  const totalPnl = executed.reduce((s, r) => s + r.total_pnl_abs, 0);
  const totalTrades = executed.reduce((s, r) => s + r.trades, 0);
  const totalWins = executed.reduce((s, r) => s + r.wins, 0);
  const overallWinRate = totalTrades > 0 ? (totalWins / totalTrades) * 100 : 0;
  const starting = state.starting_capital ?? 1_000_000;
  const overallPct = starting > 0 ? (totalPnl / starting) * 100 : 0;

  return (
    <div className="strategy-summary-widget">
      <div className="strategy-summary-overview">
        <div className="strategy-summary-stat-card">
          <div className="strategy-summary-stat-label">Total P&L</div>
          <div className={`strategy-summary-stat-value ${cls(totalPnl)}`}>
            {fmt(totalPnl, "₹")}
          </div>
          <div className={`strategy-summary-stat-sub ${cls(overallPct)}`}>
            {pctFmt(overallPct)}
          </div>
        </div>
        <div className="strategy-summary-stat-card">
          <div className="strategy-summary-stat-label">Trades</div>
          <div className="strategy-summary-stat-value">{totalTrades}</div>
          <div className="strategy-summary-stat-sub">
            {totalWins}W / {totalTrades - totalWins}L
          </div>
        </div>
        <div className="strategy-summary-stat-card">
          <div className="strategy-summary-stat-label">Win Rate</div>
          <div className={`strategy-summary-stat-value ${cls(overallWinRate - 50)}`}>
            {overallWinRate.toFixed(0)}%
          </div>
        </div>
      </div>

      <div className="strategy-summary-list">
        {executed.map((row) => (
          <StrategyRow key={row.key} row={row} />
        ))}
      </div>

      <div className="widget-as-of lt-section-timestamps">
        <TimestampLabel at={state.last_tick_at} label="Last tick" />
        <TimestampLabel at={state.updated_at} label="State" />
      </div>
    </div>
  );
}
