"""Compute listing performance for recent IPOs via yfinance."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

import yfinance as yf

from app.config import SCAN_MAX_WORKERS
from app.utils.network import without_proxy
from app.utils.yfinance_quiet import quiet_yfinance

logger = logging.getLogger(__name__)


def _yf_symbols(symbol: str) -> list[str]:
    # NSE IPOs: try NSE only first (avoids duplicate delisted warnings for .BO)
    return [f"{symbol}.NS"]


def _fetch_price_history(
    symbol: str,
    listing_date: datetime,
) -> tuple[str | None, object | None]:
    """Return (yf_symbol, history DataFrame) for first exchange with data."""
    start = listing_date - timedelta(days=2)
    end = datetime.now() + timedelta(days=1)

    symbols = _yf_symbols(symbol)
    # Fallback to BSE only if NSE has no data
    symbols.append(f"{symbol}.BO")

    with quiet_yfinance():
        for yf_symbol in symbols:
            try:
                with without_proxy():
                    df = yf.Ticker(yf_symbol).history(
                        start=start, end=end, auto_adjust=True, raise_errors=False
                    )
            except Exception:
                continue
            if df is not None and not df.empty:
                return yf_symbol, df
    return None, None


def _enrich_ipo(row: dict) -> dict:
    listing_dt = datetime.strptime(row["listing_date"], "%Y-%m-%d")
    issue_price = row.get("issue_price")

    yf_symbol, history = _fetch_price_history(row["symbol"], listing_dt)

    listing_open = None
    listing_close = None
    listing_high = None
    current_price = None

    if history is not None and not history.empty:
        # First session on/after listing date
        on_or_after = history[history.index.date >= listing_dt.date()]
        bar = on_or_after.iloc[0] if not on_or_after.empty else history.iloc[0]
        listing_open = round(float(bar["Open"]), 2)
        listing_close = round(float(bar["Close"]), 2)
        listing_high = round(float(bar["High"]), 2)
        current_price = round(float(history["Close"].iloc[-1]), 2)

    def pct(from_val: float | None, to_val: float | None) -> float | None:
        if from_val is None or to_val is None or from_val == 0:
            return None
        return round(((to_val - from_val) / from_val) * 100, 2)

    listing_day_gain_pct = pct(issue_price, listing_close)
    gain_vs_issue_pct = pct(issue_price, current_price)
    gain_vs_listing_close_pct = pct(listing_close, current_price)
    gain_listing_open_to_current_pct = pct(listing_open, current_price)

    status = "listed"
    if current_price is None:
        status = "no_market_data"

    return {
        **row,
        "yf_symbol": yf_symbol,
        "listing_open": listing_open,
        "listing_close": listing_close,
        "listing_high": listing_high,
        "current_price": current_price,
        "listing_day_gain_pct": listing_day_gain_pct,
        "gain_vs_issue_pct": gain_vs_issue_pct,
        "gain_vs_listing_close_pct": gain_vs_listing_close_pct,
        "gain_listing_open_to_current_pct": gain_listing_open_to_current_pct,
        "status": status,
    }


def enrich_ipos_parallel(rows: list[dict]) -> list[dict]:
    if not rows:
        return []

    workers = min(SCAN_MAX_WORKERS, max(1, len(rows)))
    results: list[dict] = []

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_enrich_ipo, row): row for row in rows}
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception:
                logger.exception("IPO enrich failed for %s", futures[future].get("symbol"))

    results.sort(key=lambda r: r["listing_date"], reverse=True)
    return results
