"""Volatility Squeeze screener — tight ranges primed to expand.

Built for sideways / fluctuating markets: finds stocks coiling in a narrow
range with contracting ATR and (optionally) drying-up volume — the classic
precondition for a powerful range expansion. These are setups to watch, not
chases: the entry is the range-high breakout.

Strategy per match: enter on a close above the range high, target the
measured move (range height added to the breakout), stop at the range low.
"""

from __future__ import annotations

import logging
import math

from app.services.price_history import load_daily_history
from app.services.scan_context import symbol_meta
from app.services.scan_definitions import default_params
from app.services.scan_filters import liquidity_reject, reject as _reject
from ta.trend import SMAIndicator
from ta.volatility import AverageTrueRange

logger = logging.getLogger(__name__)

MIN_BARS = 120
ATR_BASELINE_DAYS = 252


def scan_vol_squeeze_symbol(symbol: str, options: dict | None = None) -> dict | None:
    opts = {**default_params("vol_squeeze"), **(options or {})}
    range_days = int(opts.get("range_days", 20))
    max_range_pct = float(opts.get("max_range_pct", 8))
    max_atr_ratio = float(opts.get("max_atr_ratio", 0.75))
    max_dist_high = float(opts.get("max_dist_from_range_high_pct", 5))
    require_dryup = bool(opts.get("require_volume_dryup", True))
    max_dryup_ratio = float(opts.get("max_volume_dryup_ratio", 0.8))

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

        if bool(opts.get("require_above_sma200", False)):
            if len(df) < 200:
                return _reject("SMA200 not available (need 200+ bars)")
            sma200_series = SMAIndicator(close=df["close"], window=200).sma_indicator()
            sma200 = float(sma200_series.iloc[-1])
            if math.isnan(sma200):
                return _reject("SMA200 not available (need 200+ bars)")
            if close <= sma200:
                return _reject(
                    f"long-term downtrend (price {close:.2f} ≤ SMA200 {sma200:.2f})"
                )

        window = df.tail(range_days)
        range_high = float(window["high"].max())
        range_low = float(window["low"].min())
        if range_low <= 0:
            return _reject("invalid range lows")
        range_pct = (range_high - range_low) / range_low * 100.0
        if range_pct > max_range_pct:
            return _reject(
                f"{range_days}-day range {range_pct:.1f}% too wide (max {max_range_pct:g}%)"
            )

        dist_high_pct = (range_high - close) / range_high * 100.0
        if dist_high_pct > max_dist_high:
            return _reject(
                f"{dist_high_pct:.1f}% below range high (max {max_dist_high:g}%) — "
                "not positioned for the break"
            )

        atr_series = AverageTrueRange(
            high=df["high"], low=df["low"], close=df["close"], window=14
        ).average_true_range()
        atr_series = atr_series.dropna()
        if len(atr_series) < 30:
            return _reject("ATR history too short")
        atr_now = float(atr_series.iloc[-1])
        atr_baseline = float(atr_series.tail(ATR_BASELINE_DAYS).mean())
        if atr_baseline <= 0:
            return _reject("ATR baseline unavailable")
        atr_ratio = atr_now / atr_baseline
        if atr_ratio > max_atr_ratio:
            return _reject(
                f"volatility not contracting (ATR at {atr_ratio:.2f}× its 1y average, "
                f"max {max_atr_ratio:g}×)"
            )

        dryup_ratio = None
        if "volume" in df.columns:
            vols = df["volume"].dropna()
            vols = vols[vols > 0]
            if len(vols) >= 55:
                recent = float(vols.tail(5).mean())
                baseline = float(vols.iloc[:-5].tail(50).mean())
                if baseline > 0:
                    dryup_ratio = round(recent / baseline, 2)
        if require_dryup:
            if dryup_ratio is None:
                return _reject("volume data unavailable for dry-up check")
            if dryup_ratio > max_dryup_ratio:
                return _reject(
                    f"volume not drying up ({dryup_ratio}× vs max {max_dryup_ratio:g}× of 50d avg)"
                )

        entry = round(range_high, 2)
        target = round(range_high + (range_high - range_low), 2)
        stop = round(range_low, 2)
        risk = entry - stop
        rr = round((target - entry) / risk, 2) if risk > 0 else None

        meta = symbol_meta(symbol)
        return {
            "symbol": symbol,
            "company_name": meta["company_name"],
            "industry": meta["industry"],
            "market_cap_cr": meta["market_cap_cr"],
            "price": round(close, 2),
            "range_days": range_days,
            "range_high": round(range_high, 2),
            "range_low": round(range_low, 2),
            "range_pct": round(range_pct, 2),
            "dist_from_range_high_pct": round(dist_high_pct, 2),
            "atr_ratio": round(atr_ratio, 2),
            "volume_dryup_ratio": dryup_ratio,
            "entry_price": entry,
            "target_price": target,
            "stop_price": stop,
            "reward_risk": rr,
        }
    except Exception:
        logger.exception("Error scanning %s in Volatility Squeeze screener", symbol)
        return None
