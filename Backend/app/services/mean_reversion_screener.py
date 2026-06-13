"""Mean Reversion screener — buy quality uptrends pulled back to oversold.

Built for choppy / fluctuating markets where breakouts fail: instead of
chasing strength, it waits for a stock in a long-term uptrend to dip to an
oversold RSI, then plays the snap-back to its 20-day mean.

Strategy per match: enter near the current price, target the 20-day SMA,
stop at an ATR multiple below entry. Matches carry entry/target/stop and the
reward:risk so the trade plan is visible up front.
"""

from __future__ import annotations

import logging
import math

from app.services.breakout_volume import compute_volume_metrics
from app.services.price_history import load_daily_history
from app.services.scan_context import symbol_meta
from app.services.scan_definitions import default_params
from app.services.scan_filters import liquidity_reject, reject as _reject
from ta.momentum import RSIIndicator
from ta.trend import SMAIndicator
from ta.volatility import AverageTrueRange

logger = logging.getLogger(__name__)

MIN_BARS = 60


def _last(series) -> float | None:
    if series is None or len(series) == 0:
        return None
    val = float(series.iloc[-1])
    return None if math.isnan(val) else val


def scan_mean_reversion_symbol(symbol: str, options: dict | None = None) -> dict | None:
    opts = {**default_params("mean_reversion"), **(options or {})}
    max_rsi = float(opts.get("max_rsi", 35))
    min_pullback = float(opts.get("min_pullback_pct", 5))
    max_pullback = float(opts.get("max_pullback_pct", 20))
    atr_stop_multiple = float(opts.get("atr_stop_multiple", 1.5))
    min_rr = float(opts.get("min_reward_risk", 1.0))

    try:
        df = load_daily_history(symbol, period="1y", min_rows=MIN_BARS)
        if df is None or df.empty or len(df) < MIN_BARS:
            return _reject(f"insufficient daily history (need {MIN_BARS}+ bars)")

        liq_reason = liquidity_reject(
            df,
            min_price=float(opts.get("min_price", 0) or 0),
            min_avg_turnover_cr=float(opts.get("min_avg_turnover_cr", 0) or 0),
        )
        if liq_reason:
            return _reject(liq_reason)

        close = float(df["close"].iloc[-1])

        sma200 = None
        if bool(opts.get("require_above_sma200", True)):
            if len(df) < 200:
                return _reject("SMA200 not available (need 200+ bars)")
            sma200 = _last(SMAIndicator(close=df["close"], window=200).sma_indicator())
            if sma200 is None:
                return _reject("SMA200 not available (need 200+ bars)")
            if close <= sma200:
                return _reject(
                    f"long-term downtrend (price {close:.2f} ≤ SMA200 {sma200:.2f})"
                )

        rsi = _last(RSIIndicator(close=df["close"], window=14).rsi())
        if rsi is None:
            return _reject("RSI not available (not enough history)")
        if rsi > max_rsi:
            return _reject(f"not oversold (RSI {rsi:.1f} > {max_rsi:g})")

        high_20d = float(df["high"].tail(20).max())
        pullback_pct = (high_20d - close) / high_20d * 100.0 if high_20d > 0 else 0.0
        if pullback_pct < min_pullback:
            return _reject(
                f"only {pullback_pct:.1f}% off 20-day high (need {min_pullback:g}%+ dip)"
            )
        if pullback_pct > max_pullback:
            return _reject(
                f"{pullback_pct:.1f}% off 20-day high — falling knife (max {max_pullback:g}%)"
            )

        sma20 = _last(SMAIndicator(close=df["close"], window=20).sma_indicator())
        if sma20 is None:
            return _reject("SMA20 not available")
        if sma20 <= close:
            return _reject("already at/above the 20-day mean — no snap-back room")

        atr = _last(
            AverageTrueRange(
                high=df["high"], low=df["low"], close=df["close"], window=14
            ).average_true_range()
        )
        if atr is None or atr <= 0:
            return _reject("ATR not available")

        target = round(sma20, 2)
        stop = round(close - atr_stop_multiple * atr, 2)
        risk = close - stop
        reward = target - close
        if risk <= 0:
            return _reject("invalid stop (ATR too small)")
        rr = round(reward / risk, 2)
        if rr < min_rr:
            return _reject(f"reward:risk {rr} below minimum {min_rr:g}")

        metrics = {"avg_volume": None, "recent_volume": None, "volume_ratio": None, "volume_confirmed": False}
        if "volume" in df.columns:
            metrics = compute_volume_metrics(
                df["volume"].tolist(),
                average_window_days=50,
                recent_lookback_days=5,
                min_breakout_volume_multiple=1.0,
            )

        meta = symbol_meta(symbol)
        return {
            "symbol": symbol,
            "company_name": meta["company_name"],
            "industry": meta["industry"],
            "market_cap_cr": meta["market_cap_cr"],
            "price": round(close, 2),
            "rsi": round(rsi, 2),
            "sma_20": round(sma20, 2),
            "sma_200": round(sma200, 2) if sma200 is not None else None,
            "atr": round(atr, 2),
            "high_20d": round(high_20d, 2),
            "pullback_pct": round(pullback_pct, 2),
            "entry_price": round(close, 2),
            "target_price": target,
            "stop_price": stop,
            "reward_risk": rr,
            "avg_volume": metrics["avg_volume"],
            "recent_volume": metrics["recent_volume"],
            "volume_ratio": metrics["volume_ratio"],
        }
    except Exception:
        logger.exception("Error scanning %s in Mean Reversion screener", symbol)
        return None
