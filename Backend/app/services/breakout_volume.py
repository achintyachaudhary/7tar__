"""Volume-confirmation helper for breakout screeners.

A genuine breakout is accompanied by volume well above the 50-day average,
signalling institutional participation. This module computes that ratio from a
daily volume series.
"""

from __future__ import annotations

from typing import Any, Iterable

import pandas as pd


def compute_volume_metrics(
    daily_volumes: Iterable[Any],
    *,
    average_window_days: int = 50,
    recent_lookback_days: int = 5,
    min_breakout_volume_multiple: float = 1.5,
) -> dict[str, Any]:
    """
    Compute breakout volume confirmation from a daily volume series.

    - baseline_avg: mean daily volume over `average_window_days` that precede the
      most recent `recent_lookback_days` (so the recent spike doesn't bias it).
    - recent_volume: the highest daily volume within the last `recent_lookback_days`.
    - volume_ratio: recent_volume / baseline_avg.
    - volume_confirmed: volume_ratio >= min_breakout_volume_multiple.
    """
    vols = [
        float(v)
        for v in daily_volumes
        if v is not None and not (isinstance(v, float) and pd.isna(v))
    ]
    vols = [v for v in vols if v > 0]

    empty = {
        "avg_volume": None,
        "recent_volume": None,
        "volume_ratio": None,
        "volume_confirmed": False,
    }

    if len(vols) < max(5, recent_lookback_days + 1):
        return empty

    recent = vols[-recent_lookback_days:]
    baseline_pool = vols[:-recent_lookback_days]
    if not baseline_pool:
        return empty

    window = min(average_window_days, len(baseline_pool))
    baseline = baseline_pool[-window:]
    baseline_avg = sum(baseline) / len(baseline)
    if baseline_avg <= 0:
        return empty

    recent_volume = max(recent)
    ratio = recent_volume / baseline_avg

    return {
        "avg_volume": round(baseline_avg, 2),
        "recent_volume": round(recent_volume, 2),
        "volume_ratio": round(ratio, 2),
        "volume_confirmed": ratio >= min_breakout_volume_multiple,
    }
