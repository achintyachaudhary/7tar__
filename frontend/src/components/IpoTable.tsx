import { useCallback, useEffect, useMemo, useState } from "react";
import { batchFetchIpoLlmResearch, fetchIpoLlmStatus } from "../api";
import { useTableSort } from "../hooks/useTableSort";
import type { IpoListing } from "../types";
import type { IpoLlmFetchStatus, IpoLlmStatusItem } from "../types/ipoResearch";
import IpoStatusBadge from "./IpoStatusBadge";
import IpoSubscriptionModal from "./IpoSubscriptionModal";
import SortableTh from "./SortableTh";
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

function statusMapFromItems(items: IpoLlmStatusItem[]): Record<string, IpoLlmStatusItem> {
  const m: Record<string, IpoLlmStatusItem> = {};
  for (const item of items) {
    m[item.symbol] = item;
  }
  return m;
}

interface IpoTableProps {
  rows: IpoListing[];
}

export default function IpoTable({ rows }: IpoTableProps) {
  const [statusBySymbol, setStatusBySymbol] = useState<Record<string, IpoLlmStatusItem>>({});
  const [fetchingSymbols, setFetchingSymbols] = useState<Set<string>>(new Set());
  const [bulkFetching, setBulkFetching] = useState(false);
  const [bulkMsg, setBulkMsg] = useState<string | null>(null);
  const [selected, setSelected] = useState<{
    symbol: string;
    companyName: string;
  } | null>(null);

  const symbols = useMemo(() => rows.map((r) => r.symbol), [rows]);

  const loadStatus = useCallback(async () => {
    if (symbols.length === 0) return;
    try {
      const res = await fetchIpoLlmStatus(symbols);
      setStatusBySymbol(statusMapFromItems(res.statuses));
    } catch {
      /* keep previous */
    }
  }, [symbols]);

  useEffect(() => {
    void loadStatus();
  }, [loadStatus]);

  const getDisplayStatus = useCallback(
    (symbol: string): IpoLlmFetchStatus => {
      if (fetchingSymbols.has(symbol)) return "fetching";
      const row = statusBySymbol[symbol];
      if (!row || row.status === "pending") return "pending";
      return row.status as IpoLlmFetchStatus;
    },
    [statusBySymbol, fetchingSymbols],
  );

  const needsFetchCount = useMemo(() => {
    return symbols.filter((s) => {
      const st = getDisplayStatus(s);
      return st === "pending" || st === "failed";
    }).length;
  }, [symbols, getDisplayStatus]);

  async function handleBulkFetch() {
    const toFetch = rows.filter((r) => {
      const st = getDisplayStatus(r.symbol);
      return st === "pending" || st === "failed";
    });
    if (toFetch.length === 0) {
      setBulkMsg("All IPOs already fetched.");
      return;
    }

    setBulkFetching(true);
    setBulkMsg(null);
    setFetchingSymbols(new Set(toFetch.map((r) => r.symbol)));

    try {
      const res = await batchFetchIpoLlmResearch(
        toFetch.map((r) => ({ symbol: r.symbol, company_name: r.company_name })),
      );
      setBulkMsg(
        `Done: ${res.fetched_count} fetched, ${res.failed_count} failed, ${res.skipped_count} skipped.`,
      );
      await loadStatus();
    } catch (err) {
      setBulkMsg(err instanceof Error ? err.message : "Batch fetch failed");
      await loadStatus();
    } finally {
      setBulkFetching(false);
      setFetchingSymbols(new Set());
    }
  }

  const openRow = (row: IpoListing) => {
    setSelected({
      symbol: row.symbol,
      companyName: row.company_name || row.symbol,
    });
  };

  const getValue = useCallback((row: IpoListing, key: string) => {
    switch (key) {
      case "symbol": return row.symbol;
      case "company_name": return row.company_name;
      case "security_type": return row.security_type;
      case "listing_date": return row.listing_date;
      case "issue_price": return row.issue_price;
      case "listing_close": return row.listing_close;
      case "current_price": return row.current_price;
      case "listing_day_gain_pct": return row.listing_day_gain_pct;
      case "gain_vs_issue_pct": return row.gain_vs_issue_pct;
      case "gain_vs_listing_close_pct": return row.gain_vs_listing_close_pct;
      default: return null;
    }
  }, []);

  const { sortedRows, sortKey, sortDir, toggleSort } = useTableSort(
    rows,
    "listing_day_gain_pct",
    "desc",
    getValue,
  );

  const selectedStatus = selected ? getDisplayStatus(selected.symbol) : "pending";
  const selectedError = selected
    ? statusBySymbol[selected.symbol]?.error_message
    : null;

  return (
    <>
      <div className="ipo-bulk-bar">
        <button
          type="button"
          className="refresh-btn"
          disabled={bulkFetching || needsFetchCount === 0}
          onClick={() => void handleBulkFetch()}
        >
          {bulkFetching
            ? "Fetching IPO subscription…"
            : `Fetch IPO subscription (${needsFetchCount} to fetch)`}
        </button>
        {bulkMsg && (
          <span className="ipo-fetch-toast" role="status">
            {bulkMsg}
          </span>
        )}
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <SortableTh label="Symbol" sortKey="symbol" activeKey={sortKey} direction={sortDir} onSort={toggleSort} />
              <SortableTh label="Company" sortKey="company_name" activeKey={sortKey} direction={sortDir} onSort={toggleSort} />
              <SortableTh label="Type" sortKey="security_type" activeKey={sortKey} direction={sortDir} onSort={toggleSort} />
              <SortableTh label="Listed" sortKey="listing_date" activeKey={sortKey} direction={sortDir} onSort={toggleSort} />
              <SortableTh label="Issue ₹" sortKey="issue_price" activeKey={sortKey} direction={sortDir} onSort={toggleSort} />
              <SortableTh label="List close ₹" sortKey="listing_close" activeKey={sortKey} direction={sortDir} onSort={toggleSort} />
              <SortableTh label="Current ₹" sortKey="current_price" activeKey={sortKey} direction={sortDir} onSort={toggleSort} />
              <SortableTh label="Day-1 %" sortKey="listing_day_gain_pct" activeKey={sortKey} direction={sortDir} onSort={toggleSort} />
              <SortableTh label="vs Issue %" sortKey="gain_vs_issue_pct" activeKey={sortKey} direction={sortDir} onSort={toggleSort} />
              <SortableTh label="vs List close %" sortKey="gain_vs_listing_close_pct" activeKey={sortKey} direction={sortDir} onSort={toggleSort} />
              <th>Subscription</th>
            </tr>
          </thead>
          <tbody>
            {sortedRows.map((row) => {
              const noData = row.status === "no_market_data";
              const rowClass = [
                "clickable-row",
                noData ? "" : (row.gain_vs_issue_pct ?? 0) >= 0 ? "bullish" : "overbought",
              ]
                .filter(Boolean)
                .join(" ");
              const st = getDisplayStatus(row.symbol);
              const sub = statusBySymbol[row.symbol]?.overall_times_subscribed;

              return (
                <tr
                  key={`${row.symbol}-${row.listing_date}`}
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
                  aria-label={`View IPO subscription for ${row.symbol}`}
                >
                  <td onClick={(e) => e.stopPropagation()}>
                    <SymbolLink symbol={row.symbol} yfSymbol={row.yf_symbol} />
                  </td>
                  <td className="company-cell" title={row.company_name}>
                    {row.company_name}
                  </td>
                  <td>{row.security_type || "—"}</td>
                  <td>{row.listing_date_display || row.listing_date}</td>
                  <td>{fmtNum(row.issue_price)}</td>
                  <td>{fmtNum(row.listing_close)}</td>
                  <td>{fmtNum(row.current_price)}</td>
                  <td><PctCell value={row.listing_day_gain_pct} /></td>
                  <td><PctCell value={row.gain_vs_issue_pct} /></td>
                  <td><PctCell value={row.gain_vs_listing_close_pct} /></td>
                  <td>
                    <IpoStatusBadge status={st} />
                    {st === "fetched" && sub != null && (
                      <span className="ipo-sub-preview"> · {sub.toFixed(2)}×</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <IpoSubscriptionModal
        symbol={selected?.symbol ?? null}
        companyName={selected?.companyName}
        fetchStatus={selectedStatus}
        errorMessage={selectedError}
        onClose={() => setSelected(null)}
      />
    </>
  );
}
