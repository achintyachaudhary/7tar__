"""Darvas Box scanner — DB daily prices only."""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

import math

from app.services.breakout_volume import compute_volume_metrics
from app.services.chart_data import _bar_time
from app.services.price_history import load_daily_history
from app.services.scan_context import symbol_meta
from app.services.scan_definitions import default_params
from app.services.scan_filters import liquidity_reject, reject as _reject
from ta.trend import SMAIndicator

logger = logging.getLogger(__name__)


def _find_darvas_boxes(
    df: pd.DataFrame,
    *,
    settle_bars: int,
    min_box_range_pct: float,
    max_box_range_pct: float,
) -> list[dict]:
    """Identify all completed Darvas boxes in the price history."""
    highs = df["high"].values
    lows = df["low"].values
    n = len(highs)
    boxes: list[dict] = []

    i = 0
    while i < n - settle_bars:
        candidate_high = highs[i]
        candidate_idx = i

        exceeded = False
        for j in range(i + 1, min(i + 1 + settle_bars, n)):
            if highs[j] > candidate_high:
                exceeded = True
                i = j
                break

        if exceeded:
            continue

        box_top = candidate_high
        box_bottom_search_start = candidate_idx
        box_bottom_search_end = candidate_idx + settle_bars

        if box_bottom_search_end >= n:
            break

        box_bottom = float(min(lows[box_bottom_search_start : box_bottom_search_end + 1]))

        if box_bottom <= 0 or box_top <= 0:
            i = box_bottom_search_end + 1
            continue

        box_range_pct = (box_top - box_bottom) / box_bottom * 100
        if box_range_pct < min_box_range_pct or box_range_pct > max_box_range_pct:
            i = box_bottom_search_end + 1
            continue

        end_idx = box_bottom_search_end
        for k in range(box_bottom_search_end + 1, n):
            close_k = float(df["close"].iloc[k])
            low_k = lows[k]
            if close_k > box_top or low_k < box_bottom:
                break
            end_idx = k

        boxes.append({
            "top": round(float(box_top), 2),
            "bottom": round(float(box_bottom), 2),
            "range_pct": round(box_range_pct, 2),
            "start_idx": candidate_idx,
            "settle_idx": box_bottom_search_end,
            "end_idx": end_idx,
            "start_date": _bar_time(df.index[candidate_idx], "1d"),
            "end_date": _bar_time(df.index[end_idx], "1d"),
        })

        i = end_idx + 1

    return boxes


def scan_darvas_symbol(symbol: str, options: dict | None = None) -> dict | None:
    """Check if a stock has a Darvas Box breakout with optional volume confirmation."""
    opts = {**default_params("darvas"), **(options or {})}
    box_lookback = int(opts.get("box_lookback", 120))
    min_bars = int(opts.get("min_bars", 60))
    settle_bars = int(opts.get("settle_bars", 3))
    min_box_range = float(opts.get("min_box_range_pct", 1.0))
    max_box_range = float(opts.get("max_box_range_pct", 15.0))
    max_breakout_pct = float(opts.get("max_breakout_pct", 10.0))
    max_days_since_breakout = int(opts.get("max_days_since_breakout", 5))
    vol_multiple = float(opts.get("min_breakout_volume_multiple", 1.5))

    try:
        df = load_daily_history(symbol, period="1y", min_rows=min_bars)
        if df is None or df.empty or len(df) < min_bars:
            return _reject(f"insufficient daily history (need {min_bars}+ bars)")

        liq_reason = liquidity_reject(
            df,
            min_price=float(opts.get("min_price", 0) or 0),
            min_avg_turnover_cr=float(opts.get("min_avg_turnover_cr", 0) or 0),
        )
        if liq_reason:
            return _reject(liq_reason)

        if bool(opts.get("require_uptrend", True)) and len(df) >= 50:
            sma50_series = SMAIndicator(close=df["close"], window=50).sma_indicator()
            sma50 = float(sma50_series.iloc[-1])
            last_close = float(df["close"].iloc[-1])
            if not math.isnan(sma50) and last_close <= sma50:
                return _reject(f"below SMA50 (price {last_close:.2f} ≤ SMA50 {sma50:.2f})")

        # Detect boxes only inside the configured lookback window
        box_df = df.tail(box_lookback) if box_lookback > 0 else df
        boxes = _find_darvas_boxes(
            box_df,
            settle_bars=settle_bars,
            min_box_range_pct=min_box_range,
            max_box_range_pct=max_box_range,
        )
        if not boxes:
            return _reject(f"no settled box in last {len(box_df)} bars")

        latest_box = boxes[-1]
        current_close = float(df["close"].iloc[-1])
        box_top = latest_box["top"]
        box_bottom = latest_box["bottom"]

        if current_close <= box_top:
            return _reject(f"price {current_close:.2f} still inside box (top {box_top})")

        n = len(box_df)
        end_idx = int(latest_box["end_idx"])
        bars_since_box = n - 1 - end_idx
        if bars_since_box > max_days_since_breakout:
            return _reject(
                f"stale breakout — box ended {bars_since_box} bars ago "
                f"(max {max_days_since_breakout})"
            )

        # The bar that ended the box must have broken UP, not down. A box that
        # fails by breakdown and later drifts above the top is not a breakout.
        if end_idx + 1 < n:
            exit_close = float(box_df["close"].iloc[end_idx + 1])
            if exit_close <= box_top:
                return _reject("box ended with a downside break, not an upside breakout")

        breakout_pct = round((current_close / box_top - 1) * 100, 2)
        if breakout_pct > max_breakout_pct:
            return _reject(
                f"breakout too extended ({breakout_pct}% above box top, max {max_breakout_pct}%)"
            )

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
                min_breakout_volume_multiple=vol_multiple,
            )

        require = bool(opts.get("require_volume_confirmation", False))
        if require and not metrics["volume_confirmed"]:
            ratio = metrics.get("volume_ratio")
            if ratio is None:
                return _reject("volume data unavailable for confirmation")
            return _reject(f"volume not confirmed ({ratio}× vs {vol_multiple}× required)")

        box_markers = [
            {
                "top": box["top"],
                "bottom": box["bottom"],
                "range_pct": box["range_pct"],
                "start_date": box["start_date"],
                "end_date": box["end_date"],
            }
            for box in boxes
        ]

        meta = symbol_meta(symbol)
        return {
            "symbol": symbol,
            "company_name": meta["company_name"],
            "price": round(current_close, 2),
            "box_top": box_top,
            "box_bottom": box_bottom,
            "box_range_pct": latest_box["range_pct"],
            "breakout_pct": breakout_pct,
            "boxes": box_markers,
            "boxes_count": len(boxes),
            "avg_volume": metrics["avg_volume"],
            "recent_volume": metrics["recent_volume"],
            "volume_ratio": metrics["volume_ratio"],
            "volume_confirmed": metrics["volume_confirmed"],
            "volume_threshold": vol_multiple,
        }
    except Exception:
        logger.exception("Error scanning %s in Darvas screener", symbol)
        return None
