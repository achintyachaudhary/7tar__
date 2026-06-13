"""OHLCV chart data — daily/weekly from DB (stock_prices_daily); no live API for stored intervals."""

from __future__ import annotations

import logging
from typing import Any

from app.services.day_scan import get_day_scan_chart
from app.services.price_history import period_cutoff_date

logger = logging.getLogger(__name__)

# UI key -> DB resample interval + history window (days)
TIMEFRAME_CONFIG: dict[str, dict[str, str]] = {
    "1D": {"period": "5d", "interval": "15m", "tv_interval": "15"},
    "1W": {"period": "1mo", "interval": "1h", "tv_interval": "60"},
    "1M": {"period": "3mo", "interval": "1d", "tv_interval": "D"},
    "3M": {"period": "6mo", "interval": "1d", "tv_interval": "D"},
    "6M": {"period": "1y", "interval": "1d", "tv_interval": "D"},
    "1Y": {"period": "2y", "interval": "1d", "tv_interval": "D"},
    "5Y": {"period": "5y", "interval": "1wk", "tv_interval": "W"},
}

VALID_TIMEFRAMES = frozenset(TIMEFRAME_CONFIG.keys())

_DB_INTERVAL: dict[str, str] = {
    "1M": "1d",
    "3M": "1d",
    "6M": "1d",
    "1Y": "1d",
    "5Y": "1wk",
}

_DB_PERIOD: dict[str, str] = {
    "1M": "3mo",
    "3M": "6mo",
    "6M": "1y",
    "1Y": "2y",
    "5Y": "5y",
}


def _normalize_symbol(symbol: str) -> str:
    symbol = symbol.upper().strip()
    if not symbol.endswith((".NS", ".BO")):
        return f"{symbol}.NS"
    return symbol


def _bar_time(idx, interval: str) -> str | int:
    """lightweight-charts: intraday uses unix seconds; daily+ uses YYYY-MM-DD."""
    if hasattr(idx, "to_pydatetime"):
        dt = idx.to_pydatetime()
    else:
        dt = idx
    if interval in ("15m", "1h", "5m", "30m", "60m", "90m"):
        return int(dt.timestamp())
    return dt.strftime("%Y-%m-%d")


def _slice_bars_by_period(bars: list[dict[str, Any]], period: str) -> list[dict[str, Any]]:
    cutoff = period_cutoff_date(period)
    if cutoff is None or not bars:
        return bars
    cutoff_str = cutoff.isoformat()
    return [b for b in bars if str(b.get("time", "")) >= cutoff_str]


def fetch_chart_bars(symbol: str, timeframe: str) -> dict[str, Any]:
    """
    Return OHLCV bars for the requested timeframe from DB when available.
    Intraday (1D/1W) is not stored — returns empty bars; use Day Scan sync for daily+.
    """
    timeframe = timeframe.upper()
    if timeframe not in TIMEFRAME_CONFIG:
        raise ValueError(f"Invalid timeframe. Use one of: {', '.join(sorted(VALID_TIMEFRAMES))}")

    symbol = _normalize_symbol(symbol)
    cfg = TIMEFRAME_CONFIG[timeframe]
    interval = cfg["interval"]

    if timeframe not in _DB_INTERVAL:
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "interval": interval,
            "bars": [],
            "tv_interval": cfg["tv_interval"],
        }

    db_interval = _DB_INTERVAL[timeframe]
    period = _DB_PERIOD[timeframe]
    raw = get_day_scan_chart(symbol, interval=db_interval)
    bars = _slice_bars_by_period(raw.get("bars") or [], period)

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "interval": db_interval,
        "bars": bars,
        "tv_interval": cfg["tv_interval"],
    }
