import type { IpoPortfolioSimulation as PortfolioData } from "../types/ipoPortfolio";
import SymbolLink from "./SymbolLink";

function formatInr(n: number) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(n);
}

function formatInrSigned(n: number) {
  const prefix = n >= 0 ? "+" : "";
  return `${prefix}${formatInr(n)}`;
}

function profitClass(n: number) {
  if (n > 0) return "ipo-profit-positive";
  if (n < 0) return "ipo-profit-negative";
  return "";
}

interface Props {
  data: PortfolioData | null;
  loading?: boolean;
  investmentLabel?: string;
}

export default function IpoPortfolioSimulationPanel({
  data,
  loading,
  investmentLabel = "₹1 lakh",
}: Props) {
  if (loading) {
    return (
      <section className="ipo-research-panel">
        <h3>₹1 lakh per IPO — what if?</h3>
        <p className="meta">Loading portfolio simulation…</p>
      </section>
    );
  }

  if (!data || data.ipo_count === 0) {
    return (
      <section className="ipo-research-panel">
        <h3>₹1 lakh per IPO — what if?</h3>
        <p className="ipo-research-hint">
          Prepare IPO data first to see returns if you had invested {investmentLabel} in each
          IPO under different entry/exit scenarios.
        </p>
      </section>
    );
  }

  const investPer = data.investment_per_ipo_inr;

  return (
    <section className="ipo-research-panel ipo-portfolio-panel">
      <h3>₹1 lakh per IPO — what if?</h3>
      <p className="ipo-research-hint">
        Hypothetical: invest <strong>{formatInr(investPer)}</strong> in each of{" "}
        <strong>{data.ipo_count}</strong> IPOs (last {data.months ?? 6} months) under four
        scenarios. Total capital deployed = {formatInr(investPer)} × IPO count per scenario.
      </p>
      <p className="meta ipo-portfolio-disclaimer">{data.disclaimer}</p>

      <div className="ipo-portfolio-cards">
        {data.scenarios.map((s) => (
          <div key={s.id} className="ipo-portfolio-card">
            <p className="ipo-portfolio-card-title">{s.label}</p>
            <p className="ipo-portfolio-card-meta">
              {s.entry_label} → {s.exit_label} · {s.ipos_included} IPOs
            </p>
            {s.ipos_included === 0 ? (
              <p className="meta">No price data for this scenario.</p>
            ) : (
              <>
                <p className={`ipo-portfolio-roi ${profitClass(s.total_profit_inr)}`}>
                  {s.portfolio_roi_pct != null
                    ? `${s.portfolio_roi_pct >= 0 ? "+" : ""}${s.portfolio_roi_pct}% portfolio ROI`
                    : "—"}
                </p>
                <p className={`ipo-portfolio-profit ${profitClass(s.total_profit_inr)}`}>
                  {formatInrSigned(s.total_profit_inr)} total P&amp;L
                </p>
                <p className="meta">
                  Invested {formatInr(s.total_invested_inr)} → final{" "}
                  {formatInr(s.total_final_value_inr)}
                </p>
                <p className="meta">
                  {s.winners} winners · {s.losers} losers
                  {s.avg_gain_pct != null && ` · avg ${s.avg_gain_pct >= 0 ? "+" : ""}${s.avg_gain_pct}% per IPO`}
                </p>
                {s.best_ipo && (
                  <p className="meta">
                    Best: <strong>{s.best_ipo.symbol}</strong>{" "}
                    {formatInrSigned(s.best_ipo.profit_inr)} ({s.best_ipo.gain_pct >= 0 ? "+" : ""}
                    {s.best_ipo.gain_pct}%)
                  </p>
                )}
                {s.worst_ipo && (
                  <p className="meta">
                    Worst: <strong>{s.worst_ipo.symbol}</strong>{" "}
                    {formatInrSigned(s.worst_ipo.profit_inr)} ({s.worst_ipo.gain_pct >= 0 ? "+" : ""}
                    {s.worst_ipo.gain_pct}%)
                  </p>
                )}
              </>
            )}
          </div>
        ))}
      </div>

      <details className="ipo-portfolio-details">
        <summary>Per-IPO breakdown ({data.per_ipo.length} rows)</summary>
        <div className="ipo-portfolio-table-wrap">
          <table className="ipo-sub-table ipo-portfolio-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Listed</th>
                {data.scenarios.map((s) => (
                  <th key={s.id} title={s.label}>
                    {s.entry_label} → {s.exit_label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.per_ipo.map((row) => (
                <tr key={row.symbol}>
                  <td>
                    <SymbolLink symbol={row.symbol} />
                  </td>
                  <td>{row.listing_date}</td>
                  {data.scenarios.map((s) => {
                    const trade = row.scenarios[s.id];
                    return (
                      <td key={s.id} className={trade ? profitClass(trade.profit_inr) : ""}>
                        {trade ? (
                          <>
                            {formatInrSigned(trade.profit_inr)}
                            <span className="meta">
                              {" "}
                              ({trade.gain_pct >= 0 ? "+" : ""}
                              {trade.gain_pct}%)
                            </span>
                          </>
                        ) : (
                          "—"
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="meta" style={{ marginTop: "0.5rem" }}>
          Columns: profit on {formatInr(investPer)} invested (return % in parentheses).
        </p>
      </details>
    </section>
  );
}
