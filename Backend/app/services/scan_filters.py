"""Shared screener filters and the reject-sentinel helpers.

Every screener returns either a match dict, a reject sentinel (so the scan log
can explain why a symbol was skipped), or None on unexpected error.
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

REJECT_TAG = "_rejected"

# Roughly one month of sessions — enough to smooth turnover without going stale.
TURNOVER_WINDOW_DAYS = 20
CRORE = 1e7


def reject(reason: str) -> dict[str, Any]:
    """Sentinel dict so job_manager can log the skip reason."""
    return {REJECT_TAG: True, "reason": reason}


def is_reject_result(result: dict[str, Any] | None) -> bool:
    return bool(result and result.get(REJECT_TAG))


def reject_reason(result: dict[str, Any] | None) -> str:
    if not result:
        return "no match"
    return str(result.get("reason") or "no match")


def liquidity_reject(
    df: pd.DataFrame,
    *,
    min_price: float = 0.0,
    min_avg_turnover_cr: float = 0.0,
) -> str | None:
    """Reject reason for illiquid / penny stocks, or None when tradeable.

    Turnover = close × volume averaged over the last TURNOVER_WINDOW_DAYS
    sessions, in ₹ Cr. Skipped when volume data is absent so price-only
    datasets aren't rejected outright.
    """
    if df is None or df.empty:
        return "no price data"

    last_close = float(df["close"].iloc[-1])
    if math.isnan(last_close):
        return "no price data"
    if min_price > 0 and last_close < min_price:
        return f"price ₹{last_close:.2f} below minimum ₹{min_price:g}"

    if min_avg_turnover_cr > 0 and "volume" in df.columns:
        tail = df.tail(TURNOVER_WINDOW_DAYS)
        turnover = (tail["close"] * tail["volume"]).dropna()
        turnover = turnover[turnover > 0]
        if not turnover.empty:
            avg_turnover_cr = float(turnover.mean()) / CRORE
            if avg_turnover_cr < min_avg_turnover_cr:
                return (
                    f"avg daily turnover ₹{avg_turnover_cr:.2f} Cr below "
                    f"minimum ₹{min_avg_turnover_cr:g} Cr"
                )
    return None


def distance_from_52w_high_pct(df: pd.DataFrame) -> float | None:
    """How far the last close sits below the trailing 52-week high, in percent."""
    if df is None or df.empty:
        return None
    window = df.tail(252)
    high = float(window["high"].max()) if "high" in window.columns else float(window["close"].max())
    close = float(window["close"].iloc[-1])
    if high <= 0 or math.isnan(high) or math.isnan(close):
        return None
    return (high - close) / high * 100.0
