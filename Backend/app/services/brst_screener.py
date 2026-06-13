"""Daily chart scanning logic for BrSt (Breakout potential) stocks."""

import logging
import math

from app.services.breakout_volume import compute_volume_metrics
from app.services.price_history import load_daily_history
from app.services.scan_context import symbol_meta
from app.services.scan_definitions import default_params
from app.services.scan_filters import (  # noqa: F401 (re-exported for callers)
    REJECT_TAG,
    is_reject_result,
    liquidity_reject,
    reject as _reject,
    reject_reason,
)
from app.services.scan_helpers import count_distinct_tests
from ta.momentum import RSIIndicator
from ta.trend import SMAIndicator

logger = logging.getLogger(__name__)


def scan_brst_symbol(symbol: str, options: dict | None = None) -> dict | None:
    """
    Check if a stock meets BrSt criteria (parameters from scan_config / UI).
    Uses DB daily prices only. Chart bars are loaded lazily in the UI.

    Returns a match dict, a reject sentinel ({_rejected, reason}), or None on error.
    """
    opts = {**default_params("brst"), **(options or {})}

    min_bars = 40
    period = str(opts.get("period", "1y"))
    max_distance = float(opts.get("max_distance_from_high_pct", 2.5))
    test_zone_pct = float(opts.get("test_zone_pct", 2.0))
    min_tests = int(opts.get("min_distinct_tests", 2))
    group_bars = int(opts.get("test_grouping_bars", 5))
    test_factor = 1.0 - test_zone_pct / 100.0

    try:
        df = load_daily_history(symbol, period=period, min_rows=min_bars)
        if df is None or df.empty or len(df) < min_bars:
            return _reject(f"insufficient daily history (need {min_bars}+ bars for {period})")

        liq_reason = liquidity_reject(
            df,
            min_price=float(opts.get("min_price", 0) or 0),
            min_avg_turnover_cr=float(opts.get("min_avg_turnover_cr", 0) or 0),
        )
        if liq_reason:
            return _reject(liq_reason)

        highest_high = float(df["high"].max())
        current_close = float(df["close"].iloc[-1])

        distance_pct = (highest_high - current_close) / highest_high * 100.0
        if distance_pct < 0:
            return _reject(f"already above {period} high ({distance_pct:.1f}% extended)")
        if distance_pct > max_distance:
            return _reject(
                f"too far below {period} high ({distance_pct:.1f}% away, max {max_distance}%)"
            )

        distinct_tests, test_points = count_distinct_tests(
            df,
            test_factor=test_factor,
            highest_high=highest_high,
            group_size=group_bars,
            time_interval="1d",
        )
        at_period_high = current_close >= test_factor * highest_high
        if distinct_tests < min_tests and not at_period_high:
            return _reject(
                f"only {distinct_tests} resistance test(s) (need {min_tests}+)"
            )

        min_multiple = float(opts.get("min_breakout_volume_multiple", 2.0))
        metrics = {
            "avg_volume": None,
            "recent_volume": None,
            "volume_ratio": None,
            "volume_confirmed": False,
        }
        if "volume" in df.columns:
            metrics = compute_volume_metrics(
                df["volume"].tolist(),
                average_window_days=50,
                recent_lookback_days=5,
                min_breakout_volume_multiple=min_multiple,
            )
        else:
            return _reject("volume data missing — run Day Scan → Fetch Volume")

        require = bool(opts.get("require_volume_confirmation", True))
        if require and not metrics["volume_confirmed"]:
            ratio = metrics.get("volume_ratio")
            if ratio is None:
                return _reject("volume data unavailable for confirmation")
            return _reject(
                f"volume not confirmed ({ratio}× vs {min_multiple}× required)"
            )

        rsi_series = RSIIndicator(close=df["close"], window=14).rsi()
        sma50_series = SMAIndicator(close=df["close"], window=50).sma_indicator()

        current_rsi = float(rsi_series.iloc[-1]) if not rsi_series.empty else 0.0
        if math.isnan(current_rsi):
            current_rsi = 0.0

        current_sma50 = float(sma50_series.iloc[-1]) if not sma50_series.empty else 0.0
        if math.isnan(current_sma50):
            current_sma50 = 0.0

        require_uptrend = bool(opts.get("require_uptrend", True))
        if require_uptrend and current_sma50 == 0.0:
            return _reject("SMA50 not available (not enough history)")
        if require_uptrend and current_close <= current_sma50:
            return _reject(f"below SMA50 (price {current_close:.2f} ≤ SMA50 {current_sma50:.2f})")

        current_sma200: float | None = None
        if bool(opts.get("require_above_sma200", False)):
            if len(df) < 200:
                return _reject("SMA200 not available (need 200+ bars)")
            sma200_series = SMAIndicator(close=df["close"], window=200).sma_indicator()
            current_sma200 = float(sma200_series.iloc[-1])
            if math.isnan(current_sma200):
                return _reject("SMA200 not available (need 200+ bars)")
            if current_close <= current_sma200:
                return _reject(
                    f"below SMA200 (price {current_close:.2f} ≤ SMA200 {current_sma200:.2f})"
                )

        min_rsi = float(opts.get("min_rsi", 60))
        if current_rsi < min_rsi:
            return _reject(f"RSI too low ({current_rsi:.1f} < {min_rsi})")
        max_rsi = float(opts.get("max_rsi", 100) or 100)
        if current_rsi > max_rsi:
            return _reject(f"RSI overheated ({current_rsi:.1f} > {max_rsi})")

        meta = symbol_meta(symbol)
        return {
            "symbol": symbol,
            "company_name": meta["company_name"],
            "price": round(current_close, 2),
            "highest_high": round(highest_high, 2),
            "distance_pct": round(distance_pct, 2),
            "tests_count": distinct_tests,
            "test_points": test_points,
            "avg_volume": metrics["avg_volume"],
            "recent_volume": metrics["recent_volume"],
            "volume_ratio": metrics["volume_ratio"],
            "volume_confirmed": metrics["volume_confirmed"],
            "volume_threshold": min_multiple,
            "rsi": round(current_rsi, 2),
            "sma_50": round(current_sma50, 2),
        }
    except Exception:
        logger.exception("Error scanning %s in BrSt screener", symbol)
        return None
