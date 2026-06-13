"""Fetch NSE bulk deals data and store in database.

Uses the NSE snapshot API for current day deals and the historical API
for backfilling. Handles NSE session/cookie requirements.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from app.db import crud
from app.db.database import SessionLocal
from app.utils.network import make_requests_session, without_proxy

logger = logging.getLogger(__name__)

_NSE_BASE = "https://www.nseindia.com"
_SNAPSHOT_URL = f"{_NSE_BASE}/api/snapshot-capital-market-largedeal"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/market-data/large-deals",
}


def _get_nse_session():
    """Create a requests session with valid NSE cookies."""
    session = make_requests_session()
    session.headers.update(_HEADERS)
    session.get(_NSE_BASE, timeout=10)
    return session


def _parse_quantity(val) -> int:
    """Parse quantity which may have commas or be a string."""
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        return int(val)
    if isinstance(val, str):
        return int(val.replace(",", "").strip())
    return 0


def _parse_price(val) -> float:
    """Parse trade price which may have commas or be a string."""
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        return float(val.replace(",", "").strip())
    return 0.0


def fetch_bulk_deals_snapshot() -> list[dict]:
    """Fetch today's bulk deals from the NSE snapshot API."""
    try:
        session = _get_nse_session()
        time.sleep(0.5)

        resp = session.get(_SNAPSHOT_URL, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        raw_deals = data.get("BULK_DEALS_DATA", [])
        if not raw_deals:
            logger.info("No bulk deals found in snapshot response")
            return []

        deals = []
        for item in raw_deals:
            deal_date_raw = item.get("BD_DT_DATE") or item.get("date") or ""
            symbol = (item.get("BD_SYMBOL") or item.get("symbol") or "").strip()
            if not symbol or not deal_date_raw:
                continue

            # Normalize date to YYYY-MM-DD
            deal_date = _normalize_date(deal_date_raw)

            deals.append({
                "deal_date": deal_date,
                "symbol": symbol,
                "security_name": (item.get("BD_SCRIP_NAME") or item.get("name") or "").strip(),
                "client_name": (item.get("BD_CLIENT_NAME") or item.get("clientName") or "").strip(),
                "buy_sell": (item.get("BD_BUY_SELL") or item.get("buySell") or "").strip().upper(),
                "quantity": _parse_quantity(item.get("BD_QTY_TRD") or item.get("qty") or 0),
                "trade_price": _parse_price(item.get("BD_TP_WATP") or item.get("watp") or 0),
                "remarks": (item.get("BD_REMARKS") or item.get("remarks") or "").strip() or None,
            })

        logger.info("Fetched %d bulk deals from NSE snapshot", len(deals))
        return deals

    except Exception:
        logger.exception("Failed to fetch bulk deals from NSE")
        return []


def _normalize_date(date_str: str) -> str:
    """Convert various NSE date formats to YYYY-MM-DD."""
    date_str = date_str.strip()

    # Already in ISO format
    if len(date_str) == 10 and date_str[4] == "-":
        return date_str

    # dd-MMM-yyyy (e.g. "29-May-2026")
    for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    return date_str


def fetch_and_store_bulk_deals() -> dict:
    """Main entry point: fetch bulk deals and save to DB. Returns stats."""
    start = time.time()

    deals = fetch_bulk_deals_snapshot()
    if not deals:
        return {"status": "no_data", "count": 0, "duration_sec": time.time() - start}

    with SessionLocal() as db:
        inserted = crud.upsert_bulk_deals(db, deals)

    duration = time.time() - start
    logger.info("Stored %d new bulk deals (of %d fetched) in %.1fs", inserted, len(deals), duration)

    return {
        "status": "completed",
        "count": inserted,
        "total_fetched": len(deals),
        "duration_sec": duration,
    }


def _symbol_keys(symbol: str) -> list[str]:
    """NSE bulk symbols are bare tickers; price DB often uses .NS suffix."""
    s = symbol.upper().strip()
    keys = [s]
    if not s.endswith((".NS", ".BO")):
        keys.append(f"{s}.NS")
    else:
        bare = s.rsplit(".", 1)[0]
        if bare not in keys:
            keys.append(bare)
    return keys


def _yf_symbol(symbol: str) -> str:
    s = symbol.upper().strip()
    if not s.endswith((".NS", ".BO")):
        return f"{s}.NS"
    return s


def _get_closes_from_db(db, symbol: str, deal_date: str) -> tuple[float | None, float | None]:
    """Return (close on deal session date, prior trading day close)."""
    from app.db.models import StockPriceDaily

    for sym in _symbol_keys(symbol):
        row = (
            db.query(StockPriceDaily.close, StockPriceDaily.trade_date)
            .filter(
                StockPriceDaily.symbol == sym,
                StockPriceDaily.trade_date <= deal_date,
            )
            .order_by(StockPriceDaily.trade_date.desc())
            .first()
        )
        if not row:
            continue
        close_deal, session_date = row[0], row[1]
        prev = (
            db.query(StockPriceDaily.close)
            .filter(
                StockPriceDaily.symbol == sym,
                StockPriceDaily.trade_date < session_date,
            )
            .order_by(StockPriceDaily.trade_date.desc())
            .first()
        )
        if prev and prev[0] and prev[0] > 0:
            return close_deal, prev[0]
        return close_deal, None
    return None, None


def _day_change_from_yfinance(symbol: str, deal_date: str) -> float | None:
    """Fallback: % change on deal_date vs previous session via yfinance."""
    try:
        import yfinance as yf

        yf_sym = _yf_symbol(symbol)
        dt = datetime.strptime(deal_date, "%Y-%m-%d")
        start = (dt - timedelta(days=14)).strftime("%Y-%m-%d")
        end = (dt + timedelta(days=1)).strftime("%Y-%m-%d")
        with without_proxy():
            df = yf.Ticker(yf_sym).history(start=start, end=end, auto_adjust=True)
        if df is None or df.empty:
            return None
        df = df.sort_index()
        closes: list[float] = []
        for idx, row in df.iterrows():
            day = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]
            if day <= deal_date:
                closes.append(float(row["Close"]))
        if len(closes) < 2:
            return None
        close_deal = closes[-1]
        close_prev = closes[-2]
        if close_prev <= 0:
            return None
        return round((close_deal - close_prev) / close_prev * 100, 2)
    except Exception:
        logger.debug("yfinance 1D change failed for %s on %s", symbol, deal_date, exc_info=True)
        return None


def _get_market_caps_from_db(db, symbols: list[str]) -> dict[str, float | None]:
    from app.db.models import DayScanSnapshot

    caps: dict[str, float | None] = {}
    for sym in symbols:
        for key in _symbol_keys(sym):
            row = db.get(DayScanSnapshot, key)
            if row and row.market_cap_cr is not None:
                caps[sym] = row.market_cap_cr
                break
        if sym not in caps:
            caps[sym] = None
    return caps


def enrich_bulk_deals(deals: list[dict]) -> list[dict]:
    """Add amount, market_cap_cr, and deal-date 1D % change (DB then yfinance)."""
    if not deals:
        return deals

    symbols = list({d["symbol"] for d in deals})
    yf_pending: set[tuple[str, str]] = set()

    with SessionLocal() as db:
        market_caps = _get_market_caps_from_db(db, symbols)
        for d in deals:
            d["amount"] = round(d["quantity"] * d["trade_price"], 2)
            d["market_cap_cr"] = market_caps.get(d["symbol"])
            close_d, close_prev = _get_closes_from_db(db, d["symbol"], d["deal_date"])
            if close_d and close_prev and close_prev > 0:
                d["change_1d_pct"] = round((close_d - close_prev) / close_prev * 100, 2)
            else:
                d["change_1d_pct"] = None
                yf_pending.add((d["symbol"], d["deal_date"]))

    yf_cache: dict[tuple[str, str], float | None] = {}
    for sym, deal_date in yf_pending:
        if (sym, deal_date) not in yf_cache:
            yf_cache[(sym, deal_date)] = _day_change_from_yfinance(sym, deal_date)
            time.sleep(0.15)

    for d in deals:
        if d.get("change_1d_pct") is None:
            d["change_1d_pct"] = yf_cache.get((d["symbol"], d["deal_date"]))

    return deals


def build_client_analytics(deals: list[dict]) -> list[dict]:
    """Group enriched deals by client, then by stock."""
    by_client: dict[str, dict] = defaultdict(lambda: {"deals": [], "by_symbol": defaultdict(list)})

    for d in deals:
        client = d.get("client_name") or "Unknown"
        by_client[client]["deals"].append(d)
        by_client[client]["by_symbol"][d["symbol"]].append(d)

    clients_out: list[dict] = []
    for client_name in sorted(by_client.keys()):
        bucket = by_client[client_name]
        all_deals = bucket["deals"]
        stocks_out: list[dict] = []

        for symbol in sorted(bucket["by_symbol"].keys()):
            symbol_deals = bucket["by_symbol"][symbol]
            buy_amt = sum(x["amount"] for x in symbol_deals if x.get("buy_sell") == "BUY")
            sell_amt = sum(x["amount"] for x in symbol_deals if x.get("buy_sell") == "SELL")
            stocks_out.append({
                "symbol": symbol,
                "security_name": symbol_deals[0].get("security_name"),
                "deal_count": len(symbol_deals),
                "total_buy_amount": round(buy_amt, 2),
                "total_sell_amount": round(sell_amt, 2),
                "deals": symbol_deals,
            })

        total_buy = sum(x["amount"] for x in all_deals if x.get("buy_sell") == "BUY")
        total_sell = sum(x["amount"] for x in all_deals if x.get("buy_sell") == "SELL")
        unique_stocks = len(bucket["by_symbol"])

        total_volume = total_buy + total_sell

        clients_out.append({
            "client_name": client_name,
            "deal_count": len(all_deals),
            "unique_stocks": unique_stocks,
            "total_buy_amount": round(total_buy, 2),
            "total_sell_amount": round(total_sell, 2),
            "total_volume": round(total_volume, 2),
            "stocks": stocks_out,
        })

    clients_out.sort(key=lambda c: -c["total_volume"])
    return clients_out
