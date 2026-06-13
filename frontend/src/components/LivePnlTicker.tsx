import { useLiveTradeSSE } from "../context/LiveTradeSSEContext";
import TimestampLabel from "./TimestampLabel";

function fmt(v: number | null | undefined): string {
  if (v == null) return "—";
  const sign = v >= 0 ? "+" : "";
  return `${sign}₹${v.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

function pctFmt(v: number | null | undefined): string {
  if (v == null) return "";
  const sign = v >= 0 ? "+" : "";
  return `(${sign}${v.toFixed(2)}%)`;
}

export default function LivePnlTicker() {
  const { state, trades, loading } = useLiveTradeSSE();

  if (loading || !state) return null;

  const openTrades = trades.filter((t) => t.status === "open");
  if (openTrades.length === 0 && (state.realized_pnl ?? 0) === 0) return null;

  const unrealized = openTrades.reduce((sum, t) => {
    const lp = t.last_price ?? t.entry_price;
    return sum + t.qty * (lp - t.entry_price);
  }, 0);

  const realized = state.realized_pnl ?? 0;
  const totalPnl = realized + unrealized;
  const starting = state.starting_capital ?? 1_000_000;
  const totalPct = starting > 0 ? (totalPnl / starting) * 100 : 0;
  const cls = totalPnl >= 0 ? "positive" : "negative";

  const cashLeft = state.available_cash ?? starting;

  return (
    <div
      className="live-pnl-ticker"
      title={`Wallet: ${fmt(cashLeft)} left of ${fmt(starting)} | Realized: ${fmt(realized)} | Unrealized: ${fmt(unrealized)}`}
    >
      <span className="live-pnl-label">Wallet</span>
      <span className="live-pnl-value">{fmt(cashLeft)}</span>
      <span className="live-pnl-label">P&L</span>
      <span className={`live-pnl-value ${cls}`}>
        {fmt(totalPnl)} {pctFmt(totalPct)}
      </span>
      <TimestampLabel at={state.last_tick_at} label="Tick" />
    </div>
  );
}
