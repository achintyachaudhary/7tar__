"""Multi-year chart scanning logic for long-term breakout potential stocks."""

import logging
import math

from app.services.breakout_volume import compute_volume_metrics
from app.services.price_history import load_daily_history
from app.services.scan_context import symbol_meta
from app.services.scan_definitions import default_params
from app.services.scan_filters import liquidity_reject, reject as _reject
from app.services.scan_helpers import count_distinct_tests, resample_weekly_df
from ta.momentum import RSIIndicator
from ta.trend import SMAIndicator

logger = logging.getLogger(__name__)


def scan_multi_year_symbol(symbol: str, options: dict | None = None) -> dict | None:
    """
    Multi Year Breakout: weekly resistance from DB daily data resampled to weekly.
    Chart bars are loaded lazily in the UI.
    """
    opts = {**default_params("multi_year"), **(options or {})}

    period = str(opts.get("period", "3y"))
    min_weeks = 50
    max_distance = float(opts.get("max_distance_from_high_pct", 3.0))
    test_zone_pct = float(opts.get("test_zone_pct", 2.5))
    min_tests = int(opts.get("min_distinct_tests", 2))
    group_weeks = int(opts.get("test_grouping_weeks", 3))
    test_factor = 1.0 - test_zone_pct / 100.0

    try:
        daily = load_daily_history(symbol, period=period, min_rows=min_weeks * 4)
        if daily is None or daily.empty:
            return _reject(f"insufficient daily history (need ~{min_weeks} weeks for {period})")

        liq_reason = liquidity_reject(
            daily,
            min_price=float(opts.get("min_price", 0) or 0),
            min_avg_turnover_cr=float(opts.get("min_avg_turnover_cr", 0) or 0),
        )
        if liq_reason:
            return _reject(liq_reason)

        df = resample_weekly_df(daily)
        if df.empty or len(df) < min_weeks:
            return _reject(f"only {len(df)} weekly bars (need {min_weeks}+)")

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
            group_size=group_weeks,
            time_interval="1wk",
        )
        if distinct_tests < min_tests:
            return _reject(f"only {distinct_tests} resistance test(s) (need {min_tests}+)")

        if bool(opts.get("require_uptrend", True)):
            sma50_series = SMAIndicator(close=daily["close"], window=50).sma_indicator()
            sma50 = float(sma50_series.iloc[-1]) if not sma50_series.empty else float("nan")
            if math.isnan(sma50):
                return _reject("SMA50 not available (not enough history)")
            daily_close = float(daily["close"].iloc[-1])
            if daily_close <= sma50:
                return _reject(f"below SMA50 (price {daily_close:.2f} ≤ SMA50 {sma50:.2f})")

        current_rsi: float | None = None
        min_rsi = float(opts.get("min_rsi", 0) or 0)
        rsi_series = RSIIndicator(close=daily["close"], window=14).rsi()
        if not rsi_series.empty:
            val = float(rsi_series.iloc[-1])
            if not math.isnan(val):
                current_rsi = round(val, 2)
        if min_rsi > 0:
            if current_rsi is None:
                return _reject("RSI not available (not enough history)")
            if current_rsi < min_rsi:
                return _reject(f"RSI too low ({current_rsi:.1f} < {min_rsi})")

        min_multiple = float(opts.get("min_breakout_volume_multiple", 1.5))
        metrics = {
            "avg_volume": None,
            "recent_volume": None,
            "volume_ratio": None,
            "volume_confirmed": False,
        }
        if "volume" in daily.columns:
            metrics = compute_volume_metrics(
                daily["volume"].tolist(),
                average_window_days=50,
                recent_lookback_days=10,
                min_breakout_volume_multiple=min_multiple,
            )

        require = bool(opts.get("require_volume_confirmation", False))
        if require and not metrics["volume_confirmed"]:
            ratio = metrics.get("volume_ratio")
            if ratio is None:
                return _reject("volume data unavailable for confirmation")
            return _reject(f"volume not confirmed ({ratio}× vs {min_multiple}× required)")

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
            "rsi": current_rsi,
        }
    except Exception:
        logger.exception("Error scanning %s in Multi Year screener", symbol)
        return None
