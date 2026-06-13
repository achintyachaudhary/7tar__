"""Load daily OHLCV history from the database only (stock_prices_daily).

During scans, prices are bulk-preloaded into ScanContext — workers do not open
DB connections. Run Day Scan / NSE 1Day sync first to populate stock_prices_daily.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

import pandas as pd

from app.services.scan_context import get_scan_context, normalize_symbol

logger = logging.getLogger(__name__)

_PERIOD_DAYS = {
    "3mo": 95,
    "6mo": 190,
    "1y": 370,
    "2y": 740,
    "3y": 1100,
    "5y": 1830,
    "max": 100000,
}


def period_cutoff_date(period: str, anchor: date | None = None) -> date | None:
    days = _PERIOD_DAYS.get(period, 190)
    if days >= 100000:
        return None
    ref = anchor or date.today()
    return ref - timedelta(days=days)


def _bars_to_df(bars: list[dict], *, period: str) -> Optional[pd.DataFrame]:
    if not bars:
        return None

    since = period_cutoff_date(period)
    if since is not None:
        cutoff = since.isoformat()
        bars = [b for b in bars if str(b.get("time", "")) >= cutoff]
    if not bars:
        return None

    df = pd.DataFrame(bars)
    if "time" not in df.columns or df.empty:
        return None
    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    df = df.dropna(subset=["time"]).set_index("time").sort_index()
    for col in ("open", "high", "low", "close", "volume"):
        if col not in df.columns:
            df[col] = None
    return df


def _db_daily_df(symbol: str, *, period: str = "6mo") -> Optional[pd.DataFrame]:
    """Single-symbol DB read (non-scan paths only)."""
    from app.db import crud
    from app.db.database import SessionLocal

    sym = normalize_symbol(symbol)
    since = period_cutoff_date(period)

    try:
        with SessionLocal() as db:
            bars = crud.get_daily_ohlcv_bars(db, sym, since_date=since)
    except Exception:
        logger.exception("DB daily load failed for %s", symbol)
        return None

    return _bars_to_df(bars, period=period)


def load_daily_history(
    symbol: str,
    *,
    period: str = "6mo",
    min_rows: int = 40,
) -> Optional[pd.DataFrame]:
    """
    Return a daily OHLCV DataFrame from preloaded scan cache or DB.
    Returns None when data is missing or insufficient.
    """
    sym = normalize_symbol(symbol)
    ctx = get_scan_context()
    if ctx is not None:
        df = _bars_to_df(ctx.daily_bars.get(sym, []), period=period)
    else:
        df = _db_daily_df(symbol, period=period)

    if df is None or df.empty or len(df) < min_rows:
        return None
    return df


def load_minute_history(
    symbol: str,
    *,
    period: str = "7d",
) -> Optional[pd.DataFrame]:
    """Minute data is not stored in DB."""
    logger.debug("load_minute_history(%s): no DB minute store", symbol)
    return None
