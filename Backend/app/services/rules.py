"""Loader for breakout screening rules stored as JSON in app/rules/.

Rules are read from disk and cached. A file is automatically re-read when its
modification time changes, so edits take effect on the next scan without a
server restart. Built-in defaults are used if a file is missing or invalid.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

RULES_DIR = Path(__file__).resolve().parents[1] / "rules"

# Built-in fallbacks — kept in sync with the JSON files in app/rules/.
_DEFAULTS: dict[str, dict[str, Any]] = {
    "brst_breakout": {
        "id": "brst_breakout",
        "name": "BrSt Daily Breakout",
        "timeframe_label": "6 months / daily candles",
        "description": "Short-term breakout candidates near a repeatedly-tested daily resistance, confirmed by volume above the 50-day average.",
        "data": {"period": "6mo", "interval": "1d", "min_bars": 40},
        "resistance": {
            "max_distance_from_high_pct": 2.5,
            "test_zone_pct": 2.0,
            "min_distinct_tests": 2,
            "test_grouping_bars": 5,
        },
        "volume_confirmation": {
            "enabled": True,
            "average_window_days": 50,
            "recent_lookback_days": 5,
            "min_breakout_volume_multiple": 1.5,
            "require_for_match": False,
        },
    },
    "multi_year_breakout": {
        "id": "multi_year_breakout",
        "name": "Multi-Year Breakout",
        "timeframe_label": "3 years / weekly candles",
        "description": "Long-term breakout candidates from multi-year consolidation, confirmed by volume above the 50-day average.",
        "data": {"period": "3y", "interval": "weekly_from_daily", "min_weeks": 50},
        "resistance": {
            "max_distance_from_high_pct": 3.0,
            "test_zone_pct": 2.5,
            "min_distinct_tests": 2,
            "test_grouping_weeks": 3,
        },
        "volume_confirmation": {
            "enabled": True,
            "average_window_days": 50,
            "recent_lookback_days": 10,
            "min_breakout_volume_multiple": 1.5,
            "require_for_match": False,
        },
    },
}

_lock = threading.Lock()
_cache: dict[str, tuple[float, dict[str, Any]]] = {}  # rule_id -> (mtime, data)


def _strip_comments(obj: Any) -> Any:
    """Recursively drop keys that start with '_' (documentation-only)."""
    if isinstance(obj, dict):
        return {k: _strip_comments(v) for k, v in obj.items() if not str(k).startswith("_")}
    if isinstance(obj, list):
        return [_strip_comments(v) for v in obj]
    return obj


def _rule_path(rule_id: str) -> Path:
    return RULES_DIR / f"{rule_id}.json"


def get_rule(rule_id: str) -> dict[str, Any]:
    """Return the rule dict for rule_id, reading from disk (cached by mtime)."""
    path = _rule_path(rule_id)
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return dict(_DEFAULTS.get(rule_id, {}))

    with _lock:
        cached = _cache.get(rule_id)
        if cached and cached[0] == mtime:
            return cached[1]

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        data = _strip_comments(raw)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read rule %s (%s); using defaults", rule_id, exc)
        return dict(_DEFAULTS.get(rule_id, {}))

    with _lock:
        _cache[rule_id] = (mtime, data)
    return data


def list_rules() -> list[dict[str, Any]]:
    """Return all rule dicts found in the rules directory (plus known defaults)."""
    ids: set[str] = set(_DEFAULTS.keys())
    if RULES_DIR.exists():
        for p in RULES_DIR.glob("*.json"):
            ids.add(p.stem)
    return [get_rule(rid) for rid in sorted(ids)]
