import { useCallback, useState } from "react";
import { useTableSort } from "../hooks/useTableSort";
import type { SelectedStock, StockSignal } from "../types";
import SortableTh from "./SortableTh";
import StockDetailModal from "./StockDetailModal";
import SymbolLink from "./SymbolLink";

function fmtNum(v: number | null, digits = 2): string {
  if (v == null) return "—";
  return v.toFixed(digits);
}

function PctCell({ value }: { value: number | null }) {
  if (value == null) return <>—</>;
  const cls = value >= 0 ? "pct-pos" : "pct-neg";
  const sign = value >= 0 ? "+" : "";
  return (
    <span className={cls}>
      {sign}
      {value.toFixed(2)}%
    </span>
  );
}

function formatLabel(s: string): string {
  return s.replace(/_/g, " ");
}

interface StockTableProps {
  rows: StockSignal[];
}

export default function StockTable({ rows }: StockTableProps) {
  const [selected, setSelected] = useState<SelectedStock | null>(null);

  const openRow = (row: StockSignal) => {
    setSelected({ symbol: row.symbol, label: row.symbol.replace(".NS", "") });
  };

  const getValue = useCallback((row: StockSignal, key: string) => {
    switch (key) {
      case "symbol":
        return row.symbol.replace(".NS", "");
      case "price":
        return row.price;
      case "rsi":
        return row.rsi;
      case "macd":
        return row.macd;
      case "macd_signal":
        return row.macd_signal;
      case "sma_20":
        return row.sma_20;
      case "sma_50":
        return row.sma_50;
      case "change_5d_pct":
        return row.change_5d_pct;
      case "change_20d_pct":
        return row.change_20d_pct;
      case "score":
        return row.score;
      case "overall_score":
        return row.overall_score;
      case "signals":
        return row.signals.length;
      default:
        return null;
    }
  }, []);

  const { sortedRows, sortKey, sortDir, toggleSort } = useTableSort(
    rows,
    "score",
    "desc",
    getValue,
  );

  return (
    <>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <SortableTh label="Symbol" sortKey="symbol" activeKey={sortKey} direction={sortDir} onSort={toggleSort} />
              <SortableTh label="Price" sortKey="price" activeKey={sortKey} direction={sortDir} onSort={toggleSort} />
              <SortableTh label="RSI" sortKey="rsi" activeKey={sortKey} direction={sortDir} onSort={toggleSort} />
              <SortableTh label="MACD" sortKey="macd" activeKey={sortKey} direction={sortDir} onSort={toggleSort} />
              <SortableTh label="Signal" sortKey="macd_signal" activeKey={sortKey} direction={sortDir} onSort={toggleSort} />
              <SortableTh label="SMA 20" sortKey="sma_20" activeKey={sortKey} direction={sortDir} onSort={toggleSort} />
              <SortableTh label="SMA 50" sortKey="sma_50" activeKey={sortKey} direction={sortDir} onSort={toggleSort} />
              <SortableTh label="5d %" sortKey="change_5d_pct" activeKey={sortKey} direction={sortDir} onSort={toggleSort} />
              <SortableTh label="20d %" sortKey="change_20d_pct" activeKey={sortKey} direction={sortDir} onSort={toggleSort} />
              <SortableTh label="Score" sortKey="score" activeKey={sortKey} direction={sortDir} onSort={toggleSort} />
              <SortableTh label="Rating" sortKey="overall_score" activeKey={sortKey} direction={sortDir} onSort={toggleSort} />
              <SortableTh label="Signals" sortKey="signals" activeKey={sortKey} direction={sortDir} onSort={toggleSort} />
            </tr>
          </thead>
          <tbody>
            {sortedRows.map((row) => {
              const overbought = row.warnings.includes("rsi_overbought");
              const rowClass = [
                "clickable-row",
                overbought ? "overbought" : row.trend === "up" ? "bullish" : "",
              ]
                .filter(Boolean)
                .join(" ");
              const scoreClass = row.score >= 7 ? "score high" : "score";

              return (
                <tr
                  key={row.symbol}
                  className={rowClass}
                  onClick={() => openRow(row)}
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      openRow(row);
                    }
                  }}
                  role="button"
                  aria-label={`View details for ${row.symbol.replace(".NS", "")}`}
                >
                  <td onClick={(e) => e.stopPropagation()}>
                    <SymbolLink symbol={row.symbol} />
                  </td>
                  <td>₹{fmtNum(row.price)}</td>
                  <td>{fmtNum(row.rsi)}</td>
                  <td>{fmtNum(row.macd, 4)}</td>
                  <td>{fmtNum(row.macd_signal, 4)}</td>
                  <td>{fmtNum(row.sma_20)}</td>
                  <td>{fmtNum(row.sma_50)}</td>
                  <td><PctCell value={row.change_5d_pct} /></td>
                  <td><PctCell value={row.change_20d_pct} /></td>
                  <td><span className={scoreClass}>{row.score}</span></td>
                  <td>
                    {row.overall_score != null ? (
                      <span
                        className={`overall-score ${
                          row.overall_score >= 6.5
                            ? "score-green"
                            : row.overall_score >= 4
                            ? "score-amber"
                            : "score-red"
                        }`}
                        title={`Overall score: ${row.overall_score}/10`}
                      >
                        {row.overall_score}
                      </span>
                    ) : (
                      <span style={{ color: "var(--muted)", fontSize: "0.75rem" }}>—</span>
                    )}
                  </td>
                  <td>
                    <div className="tags">
                      {row.signals.map((s) => (
                        <span key={s} className="tag">{formatLabel(s)}</span>
                      ))}
                      {row.warnings.map((w) => (
                        <span key={w} className="tag warn">{formatLabel(w)}</span>
                      ))}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <StockDetailModal stock={selected} onClose={() => setSelected(null)} />
    </>
  );
}
