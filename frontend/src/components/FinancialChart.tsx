import { useState } from "react";
import type { FinancialPeriod } from "../types";

function fmtCr(v: number | null): string {
  if (v == null) return "—";
  if (v >= 1000) return `${(v / 1000).toFixed(1)}k`;
  return v.toFixed(0);
}

function fmtGrowth(v: number | null): string {
  if (v == null) return "—";
  const sign = v >= 0 ? "+" : "";
  return `${sign}${v.toFixed(0)}%`;
}

interface FinancialChartProps {
  quarterly: FinancialPeriod[];
  yearly: FinancialPeriod[];
  revenueGrowthYoy: number | null;
  revenueCagr3y: number | null;
  profitGrowthYoy: number | null;
  profitCagr3y: number | null;
}

export default function FinancialChart({
  quarterly,
  yearly,
  revenueGrowthYoy,
  revenueCagr3y,
  profitGrowthYoy,
  profitCagr3y,
}: FinancialChartProps) {
  const [mode, setMode] = useState<"quarterly" | "yearly">("quarterly");
  const periods = mode === "quarterly" ? quarterly : yearly;

  if (!periods.length) {
    return <p className="panel-empty">Financial data not available.</p>;
  }

  const maxVal = Math.max(
    ...periods.flatMap((p) => [p.revenue_cr ?? 0, p.profit_cr ?? 0]),
    1,
  );
  const latest = periods[periods.length - 1];

  return (
    <div className="insight-panel">
      <div className="panel-title-row">
        <h3 className="panel-title">P&amp;L statement</h3>
        <div className="mode-toggle">
          <button
            type="button"
            className={`mode-btn${mode === "quarterly" ? " active" : ""}`}
            onClick={() => setMode("quarterly")}
          >
            Quarterly
          </button>
          <button
            type="button"
            className={`mode-btn${mode === "yearly" ? " active" : ""}`}
            onClick={() => setMode("yearly")}
          >
            Yearly
          </button>
        </div>
      </div>

      {latest && (
        <div className="fin-legend">
          <span>
            <i className="dot revenue" /> Revenue (Cr): ₹{fmtCr(latest.revenue_cr)}
          </span>
          <span>
            <i className="dot profit" /> Profit (Cr): ₹{fmtCr(latest.profit_cr)}
          </span>
        </div>
      )}

      <div className="fin-chart">
        {periods.map((p) => (
          <div key={p.period} className="fin-bar-group">
            <div className="fin-bars">
              <div
                className="fin-bar revenue"
                style={{ height: `${((p.revenue_cr ?? 0) / maxVal) * 100}%` }}
                title={`Revenue: ₹${fmtCr(p.revenue_cr)} Cr`}
              />
              <div
                className="fin-bar profit"
                style={{ height: `${((p.profit_cr ?? 0) / maxVal) * 100}%` }}
                title={`Profit: ₹${fmtCr(p.profit_cr)} Cr`}
              />
            </div>
            <span className="fin-label">{p.label}</span>
          </div>
        ))}
      </div>

      {mode === "quarterly" && (
        <div className="fin-summary">
          <div className="fin-summary-col">
            <span className="fin-summary-head">Revenue growth</span>
            <div className="fin-summary-row">
              <span>1Y (QoQ)</span>
              <span className={growthClass(revenueGrowthYoy)}>
                {fmtGrowth(revenueGrowthYoy)}
              </span>
            </div>
            <div className="fin-summary-row">
              <span>3Y CAGR</span>
              <span className={growthClass(revenueCagr3y)}>
                {fmtGrowth(revenueCagr3y)}
              </span>
            </div>
          </div>
          <div className="fin-summary-col">
            <span className="fin-summary-head">Profit growth</span>
            <div className="fin-summary-row">
              <span>1Y (QoQ)</span>
              <span className={growthClass(profitGrowthYoy)}>
                {fmtGrowth(profitGrowthYoy)}
              </span>
            </div>
            <div className="fin-summary-row">
              <span>3Y CAGR</span>
              <span className={growthClass(profitCagr3y)}>
                {fmtGrowth(profitCagr3y)}
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function growthClass(v: number | null): string {
  if (v == null) return "";
  return v >= 0 ? "pct-pos" : "pct-neg";
}
