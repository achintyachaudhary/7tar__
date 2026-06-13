"""Shared scan utilities: vectorized tests, weekly resample, slim match payloads."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from app.services.chart_data import _bar_time

MATCH_BULK_KEYS = frozenset({"bars", "weekly_bars"})


def slim_match_payload(match: dict[str, Any]) -> dict[str, Any]:
    """Drop heavy OHLCV arrays from scan results (charts load lazily from DB)."""
    return {k: v for k, v in match.items() if k not in MATCH_BULK_KEYS}


def resample_weekly_df(daily: pd.DataFrame) -> pd.DataFrame:
    """Resample daily OHLCV to weekly (Friday) candles."""
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    cols = {c: agg[c] for c in agg if c in daily.columns}
    weekly = daily.resample("W-FRI").agg(cols)
    return weekly.dropna(subset=["close"])


def count_distinct_tests(
    df: pd.DataFrame,
    *,
    test_factor: float,
    highest_high: float,
    group_size: int,
    time_interval: str = "1d",
) -> tuple[int, list[dict[str, Any]]]:
    """
    Vectorized resistance touch counting.
    group_size is in bars (daily) or weeks (weekly index positions).
    """
    highs = df["high"].to_numpy(dtype=float)
    mask = highs >= test_factor * highest_high
    indices = np.flatnonzero(mask)
    if len(indices) == 0:
        return 0, []

    test_points: list[dict[str, Any]] = []
    for i in indices:
        idx = df.index[i]
        test_points.append({
            "time": _bar_time(idx, time_interval),
            "price": round(float(highs[i]), 2),
        })

    distinct = 1
    for i in range(1, len(indices)):
        if indices[i] - indices[i - 1] > group_size:
            distinct += 1
    return distinct, test_points
