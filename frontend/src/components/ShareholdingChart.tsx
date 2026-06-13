import { useState } from "react";
import type { ShareholdingPeriod } from "../types";

const BAR_ITEMS = [
  { key: "fii_holding_pct" as const, label: "Foreign Institutions" },
  { key: "promoter_holding_pct" as const, label: "Promoters" },
  { key: "dii_holding_pct" as const, label: "Domestic Institutions" },
  { key: "retail_and_others_pct" as const, label: "Others (public)" },
];

interface ShareholdingChartProps {
  periods: ShareholdingPeriod[];
}

const MONTH_INDEX: Record<string, number> = {
  JAN: 0, FEB: 1, MAR: 2, APR: 3, MAY: 4, JUN: 5,
  JUL: 6, AUG: 7, SEP: 8, OCT: 9, NOV: 10, DEC: 11,
};

function parseAsOf(raw: string): number {
  const m = raw.match(/^(\d{1,2})-([A-Za-z]{3})-(\d{4})$/);
  if (m) {
    const mon = MONTH_INDEX[m[2].toUpperCase()];
    if (mon !== undefined) {
      return Date.UTC(Number(m[3]), mon, Number(m[1]));
    }
  }
  const d = new Date(raw);
  return Number.isNaN(d.getTime()) ? 0 : d.getTime();
}

export default function ShareholdingChart({ periods }: ShareholdingChartProps) {
  const sorted = [...periods].sort((a, b) => parseAsOf(a.as_of) - parseAsOf(b.as_of));
  const [activeIdx, setActiveIdx] = useState(Math.max(0, sorted.length - 1));

  if (!sorted.length) {
    return <p className="panel-empty">Shareholding data not available.</p>;
  }

  const period = sorted[activeIdx] ?? sorted[sorted.length - 1];
  const totalPct = BAR_ITEMS.reduce(
    (sum, { key }) => sum + (period[key] ?? 0),
    0,
  );

  return (
    <div className="insight-panel">
      <h3 className="panel-title">Investor holding</h3>
      <div className="period-tabs">
        {sorted.map((p, i) => (
          <button
            key={p.as_of}
            type="button"
            className={`period-tab${i === activeIdx ? " active" : ""}`}
            onClick={() => setActiveIdx(i)}
          >
            {p.label}
          </button>
        ))}
      </div>
      <div className="holding-bars">
        {BAR_ITEMS.map(({ key, label }) => {
          const pct = period[key];
          if (pct == null) return null;
          return (
            <div key={key} className="holding-bar-row">
              <span className="holding-label">{label}</span>
              <div className="holding-bar-track">
                <div
                  className="holding-bar-fill"
                  style={{ width: `${Math.min(pct, 100)}%` }}
                />
              </div>
              <span className="holding-pct">{pct.toFixed(2)}%</span>
            </div>
          );
        })}
      </div>
      <p className="holding-total-meta">
        Total: {totalPct.toFixed(2)}% (promoter + FII + DII + others)
      </p>
    </div>
  );
}
