import { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchBulkDeals,
  fetchBulkDealDates,
  fetchBulkDealsAnalytics,
  triggerBulkDealsFetch,
  type BulkDeal,
  type BulkDealClientAnalytics,
  type BulkDealsAnalyticsResponse,
} from "../api";
import { formatIST, formatISTDateOnly } from "../lib/formatTime";
import TimestampLabel from "../components/TimestampLabel";
import SymbolLink from "../components/SymbolLink";

type Tab = "deals" | "analytics";
type SortField =
  | "symbol"
  | "client_name"
  | "quantity"
  | "trade_price"
  | "amount"
  | "market_cap_cr"
  | "change_1d_pct"
  | "buy_sell";
type SortDir = "asc" | "desc";

function formatQuantity(qty: number) {
  return qty.toLocaleString("en-IN");
}

function formatPrice(price: number) {
  return `₹${price.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatAmount(amount: number) {
  if (amount >= 1e7) return `₹${(amount / 1e7).toFixed(2)} Cr`;
  if (amount >= 1e5) return `₹${(amount / 1e5).toFixed(2)} L`;
  return formatPrice(amount);
}

function formatMarketCap(cr: number | null | undefined) {
  if (cr == null) return "—";
  if (cr >= 100000) return `${(cr / 100000).toFixed(2)} L Cr`;
  if (cr >= 100) return `${(cr / 100).toFixed(2)} K Cr`;
  return `${cr.toFixed(0)} Cr`;
}

function ChangeCell({ pct }: { pct: number | null | undefined }) {
  if (pct == null) return <td className="num change-cell">—</td>;
  const cls = pct >= 0 ? "positive" : "negative";
  return (
    <td className={`num change-cell ${cls}`}>
      {pct >= 0 ? "+" : ""}
      {pct.toFixed(2)}%
    </td>
  );
}

export default function BulkDealsPage() {
  const [tab, setTab] = useState<Tab>("deals");
  const [deals, setDeals] = useState<BulkDeal[]>([]);
  const [analytics, setAnalytics] = useState<BulkDealsAnalyticsResponse | null>(null);
  const [dates, setDates] = useState<string[]>([]);
  const [selectedDate, setSelectedDate] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [fetching, setFetching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [sortField, setSortField] = useState<SortField>("amount");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [filterBuySell, setFilterBuySell] = useState<"ALL" | "BUY" | "SELL">("ALL");
  const [expandedClients, setExpandedClients] = useState<Set<string>>(new Set());
  const [clientSearch, setClientSearch] = useState("");
  const [dealsLoadedAt, setDealsLoadedAt] = useState<Date | null>(null);

  const loadDates = useCallback(async () => {
    try {
      const d = await fetchBulkDealDates();
      setDates(d);
      if (d.length > 0 && !selectedDate) {
        setSelectedDate(d[0]);
      }
    } catch {
      // ignore
    }
  }, [selectedDate]);

  const loadDeals = useCallback(async (date?: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchBulkDeals(date || undefined);
      setDeals(data);
      setDealsLoadedAt(new Date());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load bulk deals");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadAnalytics = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchBulkDealsAnalytics();
      setAnalytics(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load analytics");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDates();
  }, [loadDates]);

  useEffect(() => {
    if (tab === "deals") {
      loadDeals(selectedDate || undefined);
    } else {
      loadAnalytics();
    }
  }, [selectedDate, tab, loadDeals, loadAnalytics]);

  const handleFetch = async () => {
    setFetching(true);
    setError(null);
    try {
      const result = await triggerBulkDealsFetch();
      if (result.status === "completed" || result.status === "no_data") {
        await loadDates();
        if (tab === "deals") {
          await loadDeals(selectedDate || undefined);
        } else {
          await loadAnalytics();
        }
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Fetch failed");
    } finally {
      setFetching(false);
    }
  };

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDir("desc");
    }
  };

  const filteredDeals = useMemo(() => {
    let result = deals;
    if (filterBuySell !== "ALL") {
      result = result.filter((d) => d.buy_sell === filterBuySell);
    }
    if (search.trim()) {
      const q = search.toLowerCase();
      result = result.filter(
        (d) =>
          d.symbol.toLowerCase().includes(q) ||
          (d.security_name || "").toLowerCase().includes(q) ||
          d.client_name.toLowerCase().includes(q),
      );
    }
    return [...result].sort((a, b) => {
      let av: string | number | null = a[sortField] as string | number | null;
      let bv: string | number | null = b[sortField] as string | number | null;
      if (av == null) av = sortDir === "asc" ? Infinity : -Infinity;
      if (bv == null) bv = sortDir === "asc" ? Infinity : -Infinity;
      if (typeof av === "string") av = av.toLowerCase();
      if (typeof bv === "string") bv = bv.toLowerCase();
      if (av < bv) return sortDir === "asc" ? -1 : 1;
      if (av > bv) return sortDir === "asc" ? 1 : -1;
      return 0;
    });
  }, [deals, search, sortField, sortDir, filterBuySell]);

  const filteredClients = useMemo(() => {
    if (!analytics?.clients) return [];
    if (!clientSearch.trim()) return analytics.clients;
    const q = clientSearch.toLowerCase();
    return analytics.clients.filter(
      (c) =>
        c.client_name.toLowerCase().includes(q) ||
        c.stocks.some(
          (s) =>
            s.symbol.toLowerCase().includes(q) ||
            (s.security_name || "").toLowerCase().includes(q),
        ),
    );
  }, [analytics, clientSearch]);

  const toggleClient = (name: string) => {
    setExpandedClients((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortField !== field) return <span className="sort-icon dim">⇅</span>;
    return <span className="sort-icon">{sortDir === "asc" ? "↑" : "↓"}</span>;
  };

  return (
    <div className="bulk-deals-page">
      <div className="page-header">
        <h1>Bulk Deals</h1>
        <div className="header-actions">
          <select
            value={selectedDate}
            onChange={(e) => setSelectedDate(e.target.value)}
            className="date-select"
          >
            {dates.length === 0 && <option value="">No data</option>}
            {dates.map((d) => (
              <option key={d} value={d}>
                {new Date(d + "T00:00:00").toLocaleDateString("en-IN", {
                  day: "2-digit",
                  month: "short",
                  year: "numeric",
                })}
              </option>
            ))}
          </select>
          <button
            className="btn btn-primary btn-sm"
            onClick={handleFetch}
            disabled={fetching}
            title="Fetch latest bulk deals from NSE"
          >
            {fetching ? "⟳ Fetching..." : "⟳ Fetch Now"}
          </button>
        </div>
      </div>

      <div className="bulk-deals-tabs">
        <button
          type="button"
          className={`bulk-deals-tab${tab === "deals" ? " active" : ""}`}
          onClick={() => setTab("deals")}
        >
          Deals
        </button>
        <button
          type="button"
          className={`bulk-deals-tab${tab === "analytics" ? " active" : ""}`}
          onClick={() => setTab("analytics")}
        >
          Analytics
        </button>
      </div>

      {tab === "deals" && (
        <div className="bulk-deals-controls">
          <input
            type="text"
            className="search-input"
            placeholder="Search symbol, company, or client..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <div className="filter-pills">
            {(["ALL", "BUY", "SELL"] as const).map((f) => (
              <button
                key={f}
                type="button"
                className={`pill${filterBuySell === f ? " active" : ""}${f === "BUY" ? " buy" : f === "SELL" ? " sell" : ""}`}
                onClick={() => setFilterBuySell(f)}
              >
                {f}
              </button>
            ))}
          </div>
          <span className="deal-count">{filteredDeals.length} deals</span>
          {dealsLoadedAt && (
            <TimestampLabel at={dealsLoadedAt} label="Loaded" />
          )}
          {deals[0]?.fetched_at && (
            <TimestampLabel at={deals[0].fetched_at} label="NSE fetched" />
          )}
        </div>
      )}

      {tab === "analytics" && (
        <div className="bulk-deals-controls">
          <input
            type="text"
            className="search-input"
            placeholder="Search client or stock..."
            value={clientSearch}
            onChange={(e) => setClientSearch(e.target.value)}
          />
          {analytics && (
            <span className="deal-count">
              {analytics.client_count} clients · {analytics.deal_count} deals (all dates combined, sorted by volume)
            </span>
          )}
        </div>
      )}

      {error && <div className="error-banner">{error}</div>}

      {loading ? (
        <div className="loading-state">Loading...</div>
      ) : tab === "deals" ? (
        filteredDeals.length === 0 ? (
          <div className="empty-state">
            No bulk deals found.{" "}
            {dates.length === 0 && (
              <button type="button" className="btn btn-link" onClick={handleFetch}>
                Fetch from NSE
              </button>
            )}
          </div>
        ) : (
          <div className="table-wrapper">
            <table className="bulk-deals-table">
              <thead>
                <tr>
                  <th onClick={() => handleSort("symbol")} className="sortable">
                    Symbol <SortIcon field="symbol" />
                  </th>
                  <th>Security</th>
                  <th onClick={() => handleSort("client_name")} className="sortable">
                    Client <SortIcon field="client_name" />
                  </th>
                  <th onClick={() => handleSort("buy_sell")} className="sortable">
                    B/S <SortIcon field="buy_sell" />
                  </th>
                  <th onClick={() => handleSort("quantity")} className="sortable num">
                    Qty <SortIcon field="quantity" />
                  </th>
                  <th onClick={() => handleSort("trade_price")} className="sortable num">
                    Price <SortIcon field="trade_price" />
                  </th>
                  <th onClick={() => handleSort("amount")} className="sortable num">
                    Amount <SortIcon field="amount" />
                  </th>
                  <th onClick={() => handleSort("market_cap_cr")} className="sortable num">
                    Mkt Cap <SortIcon field="market_cap_cr" />
                  </th>
                  <th onClick={() => handleSort("change_1d_pct")} className="sortable num">
                    1D % <SortIcon field="change_1d_pct" />
                  </th>
                  <th>Deal date</th>
                  <th>Fetched</th>
                </tr>
              </thead>
              <tbody>
                {filteredDeals.map((deal) => (
                  <tr key={deal.id}>
                    <td className="symbol-cell">
                      <SymbolLink symbol={deal.symbol} />
                    </td>
                    <td className="name-cell">{deal.security_name || "—"}</td>
                    <td className="client-cell">{deal.client_name}</td>
                    <td className={`bs-cell ${deal.buy_sell.toLowerCase()}`}>{deal.buy_sell}</td>
                    <td className="num">{formatQuantity(deal.quantity)}</td>
                    <td className="num">{formatPrice(deal.trade_price)}</td>
                    <td className="num amount-cell">{formatAmount(deal.amount)}</td>
                    <td className="num">{formatMarketCap(deal.market_cap_cr)}</td>
                    <ChangeCell pct={deal.change_1d_pct} />
                    <td className="lt-date-cell">{formatISTDateOnly(deal.deal_date)}</td>
                    <td className="lt-date-cell">{formatIST(deal.fetched_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      ) : filteredClients.length === 0 ? (
        <div className="empty-state">No client analytics for this date.</div>
      ) : (
        <div className="bulk-analytics-list">
          {filteredClients.map((client) => (
            <ClientAnalyticsCard
              key={client.client_name}
              client={client}
              expanded={expandedClients.has(client.client_name)}
              onToggle={() => toggleClient(client.client_name)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function ClientAnalyticsCard({
  client,
  expanded,
  onToggle,
}: {
  client: BulkDealClientAnalytics;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <div className={`bulk-analytics-client${expanded ? " expanded" : ""}`}>
      <button type="button" className="bulk-analytics-client-header" onClick={onToggle}>
        <span className="expand-icon">{expanded ? "▼" : "▶"}</span>
        <span className="client-title">{client.client_name}</span>
        <span className="client-meta">
          {client.deal_count} deals · {client.unique_stocks} stocks
        </span>
        <span className="client-volume">Vol {formatAmount(client.total_volume)}</span>
        <span className="client-amounts">
          <span className="buy-label">Buy {formatAmount(client.total_buy_amount)}</span>
          <span className="sell-label">Sell {formatAmount(client.total_sell_amount)}</span>
        </span>
      </button>
      {expanded && (
        <div className="bulk-analytics-stocks">
          {client.stocks.map((stock) => (
            <div key={stock.symbol} className="bulk-analytics-stock">
              <div className="stock-summary">
                <SymbolLink symbol={stock.symbol} className="stock-symbol" />
                <span className="stock-name">{stock.security_name || ""}</span>
                <span className="stock-count">{stock.deal_count} deal(s)</span>
                <span className="stock-buy">B {formatAmount(stock.total_buy_amount)}</span>
                <span className="stock-sell">S {formatAmount(stock.total_sell_amount)}</span>
              </div>
              <table className="bulk-analytics-deals-table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>B/S</th>
                    <th className="num">Qty</th>
                    <th className="num">Price</th>
                    <th className="num">Amount</th>
                    <th className="num">1D %</th>
                  </tr>
                </thead>
                <tbody>
                  {stock.deals.map((d) => (
                    <tr key={d.id}>
                      <td className="date-cell">{d.deal_date}</td>
                      <td className={`bs-cell ${d.buy_sell.toLowerCase()}`}>{d.buy_sell}</td>
                      <td className="num">{formatQuantity(d.quantity)}</td>
                      <td className="num">{formatPrice(d.trade_price)}</td>
                      <td className="num">{formatAmount(d.amount)}</td>
                      <ChangeCell pct={d.change_1d_pct} />
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
