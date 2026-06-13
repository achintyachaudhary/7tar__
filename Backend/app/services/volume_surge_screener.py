"""Volume Surge screener — unusual accumulation days.

Flags stocks trading at a multiple of their normal volume while closing up
and strong — the classic institutional-accumulation footprint. Works in any
market regime because it reads participation, not chart patterns.

Strategy per match: this is a watch signal, not an automatic entry — look for
follow-through above the surge-day high with the stop under the surge-day low
(both included in the payload).
"""

from __future__ import annotations

import logging
import math

from app.services.price_history import load_daily_history
from app.services.scan_context import symbol_meta
from app.services.scan_definitions import default_params
from app.services.scan_filters import liquidity_reject, reject as _reject
from ta.trend import SMAIndicator

logger = logging.getLogger(__name__)

MIN_BARS = 60
VOLUME_BASELINE_DAYS = 50


def scan_volume_surge_symbol(symbol: str, options: dict | None = None) -> dict | None:
    opts = {**default_params("volume_surge"), **(options or {})}
    min_volume_multiple = float(opts.get("min_volume_multiple", 3.0))
    min_day_change = float(opts.get("min_day_change_pct", 2.0))
    min_close_strength = float(opts.get("min_close_strength_pct", 60.0))

    try:
        df = load_daily_history(symbol, period="6mo", min_rows=MIN_BARS)
        if df is None or df.empty or len(df) < MIN_BARS:
            return _reject(f"insufficient daily history (need {MIN_BARS}+ bars)")
        if "volume" not in df.columns:
            return _reject("volume data missing — run Day Scan → Fetch Volume")

        liq_reason = liquidity_reject(
            df,
            min_price=float(opts.get("min_price", 0) or 0),
            min_avg_turnover_cr=float(opts.get("min_avg_turnover_cr", 0) or 0),
        )
        if liq_reason:
            return _reject(liq_reason)

        last = df.iloc[-1]
        prev_close = float(df["close"].iloc[-2])
        close = float(last["close"])
        high = float(last["high"])
        low = float(last["low"])
        volume = float(last["volume"] or 0)

        baseline = df["volume"].iloc[:-1].dropna()
        baseline = baseline[baseline > 0].tail(VOLUME_BASELINE_DAYS)
        if len(baseline) < 20:
            return _reject("not enough volume history for a baseline")
        avg_volume = float(baseline.mean())
        if avg_volume <= 0 or volume <= 0:
            return _reject("no tradable volume")

        volume_multiple = volume / avg_volume
        if volume_multiple < min_volume_multiple:
            return _reject(
                f"volume {volume_multiple:.1f}× of 50d avg (need {min_volume_multiple:g}×+)"
            )

        day_change_pct = (close - prev_close) / prev_close * 100 if prev_close > 0 else 0.0
        if day_change_pct < min_day_change:
            return _reject(
                f"day change {day_change_pct:+.1f}% below {min_day_change:g}% — "
                "surge without buyers"
            )

        day_range = high - low
        close_strength = ((close - low) / day_range * 100) if day_range > 0 else 100.0
        if close_strength < min_close_strength:
            return _reject(
                f"weak close ({close_strength:.0f}% of day range, need "
                f"{min_close_strength:g}%+) — sellers absorbed the volume"
            )

        if bool(opts.get("require_uptrend", True)) and len(df) >= 50:
            sma50_series = SMAIndicator(close=df["close"], window=50).sma_indicator()
            sma50 = float(sma50_series.iloc[-1])
            if not math.isnan(sma50) and close <= sma50:
                return _reject(f"below SMA50 (price {close:.2f} ≤ SMA50 {sma50:.2f})")

        meta = symbol_meta(symbol)
        return {
            "symbol": symbol,
            "company_name": meta["company_name"],
            "industry": meta["industry"],
            "market_cap_cr": meta["market_cap_cr"],
            "price": round(close, 2),
            "day_change_pct": round(day_change_pct, 2),
            "volume_multiple": round(volume_multiple, 2),
            "day_volume": round(volume),
            "avg_volume_50d": round(avg_volume),
            "close_strength_pct": round(close_strength, 1),
            "surge_high": round(high, 2),
            "surge_low": round(low, 2),
            "entry_price": round(high, 2),
            "stop_price": round(low, 2),
        }
    except Exception:
        logger.exception("Error scanning %s in Volume Surge screener", symbol)
        return None
