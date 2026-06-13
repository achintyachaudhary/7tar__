"""Scanner metadata: core criteria (fixed identity) + user-configurable parameters.

Rule JSON files under app/rules/ are deprecated — parameters are chosen in the UI
and shipped via scan_config. Core criteria describe what the algorithm always checks.
"""

from __future__ import annotations

from typing import Any

# Liquidity / quality gate shared by every screener. Penny and illiquid stocks
# produce untradeable "breakouts", so they are filtered before pattern logic runs.
_LIQUIDITY_PARAMS: list[dict[str, Any]] = [
    {"id": "min_price", "label": "Min stock price", "type": "number", "default": 20, "min": 0, "max": 500, "unit": "₹"},
    {"id": "min_avg_turnover_cr", "label": "Min avg daily turnover (20d)", "type": "number", "default": 1, "min": 0, "max": 25, "unit": "₹ Cr"},
]

_LIQUIDITY_CRITERION = {
    "id": "liquidity_gate",
    "label": "Liquidity & price floor",
    "detail": "Penny stocks and thinly traded names are rejected before pattern checks.",
}

# scan_type keys match SCAN_REGISTRY / scan_result_cache
SCAN_DEFINITIONS: dict[str, dict[str, Any]] = {
    "brst": {
        "scan_type": "brst",
        "name": "Year Breakout",
        "description": "Daily chart breakout near a repeatedly-tested resistance level.",
        "core_criteria": [
            {
                "id": "resistance_pattern",
                "label": "Resistance tested multiple times",
                "detail": "Price within max-distance % of the period high with grouped touch events.",
            },
            {
                "id": "volume_flag",
                "label": "Volume confirmation computed",
                "detail": "Recent volume vs 50-day average is calculated for each match (filter optional).",
            },
            _LIQUIDITY_CRITERION,
        ],
        "param_schema": [
            {"id": "max_distance_from_high_pct", "label": "Max distance from high", "type": "number", "default": 2.5, "min": 0.5, "max": 10, "unit": "%"},
            {"id": "test_zone_pct", "label": "Test zone width", "type": "number", "default": 2.0, "min": 0.5, "max": 5, "unit": "%"},
            {"id": "min_distinct_tests", "label": "Min resistance tests", "type": "number", "default": 2, "min": 1, "max": 10, "unit": "tests"},
            {"id": "test_grouping_bars", "label": "Test grouping (bars)", "type": "number", "default": 5, "min": 1, "max": 20, "unit": "bars"},
            {"id": "min_breakout_volume_multiple", "label": "Volume multiple", "type": "number", "default": 2.0, "min": 1, "max": 5, "unit": "×"},
            {"id": "require_volume_confirmation", "label": "Require volume confirmed", "type": "boolean", "default": True},
            {"id": "period", "label": "History period", "type": "select", "default": "1y", "options": ["3mo", "6mo", "1y"]},
            {"id": "require_uptrend", "label": "Require Uptrend (Price > SMA50)", "type": "boolean", "default": True},
            {"id": "require_above_sma200", "label": "Require long-term uptrend (Price > SMA200)", "type": "boolean", "default": False},
            {"id": "min_rsi", "label": "Min 14-day RSI", "type": "number", "default": 60, "min": 0, "max": 100, "unit": "RSI"},
            {"id": "max_rsi", "label": "Max 14-day RSI (avoid blow-off)", "type": "number", "default": 82, "min": 50, "max": 100, "unit": "RSI"},
            *_LIQUIDITY_PARAMS,
        ],
    },
    "multi_year": {
        "scan_type": "multi_year",
        "name": "Multi-Year Breakout",
        "description": "Weekly-candle breakout from multi-year consolidation.",
        "core_criteria": [
            {
                "id": "weekly_resistance",
                "label": "Multi-year weekly resistance pattern",
                "detail": "Weekly highs tested and price near the range top.",
            },
            {
                "id": "volume_flag",
                "label": "Volume confirmation computed",
                "detail": "Recent volume vs 50-day average is calculated for each match.",
            },
            _LIQUIDITY_CRITERION,
        ],
        "param_schema": [
            {"id": "max_distance_from_high_pct", "label": "Max distance from high", "type": "number", "default": 3.0, "min": 0.5, "max": 15, "unit": "%"},
            {"id": "test_zone_pct", "label": "Test zone width", "type": "number", "default": 2.5, "min": 0.5, "max": 5, "unit": "%"},
            {"id": "min_distinct_tests", "label": "Min resistance tests", "type": "number", "default": 2, "min": 1, "max": 10, "unit": "tests"},
            {"id": "test_grouping_weeks", "label": "Test grouping (weeks)", "type": "number", "default": 3, "min": 1, "max": 10, "unit": "weeks"},
            {"id": "min_breakout_volume_multiple", "label": "Volume multiple", "type": "number", "default": 1.5, "min": 1, "max": 5, "unit": "×"},
            {"id": "require_volume_confirmation", "label": "Require volume confirmed", "type": "boolean", "default": False},
            {"id": "period", "label": "History period", "type": "select", "default": "3y", "options": ["2y", "3y", "5y"]},
            {"id": "require_uptrend", "label": "Require Uptrend (Price > SMA50)", "type": "boolean", "default": True},
            {"id": "min_rsi", "label": "Min 14-day RSI", "type": "number", "default": 50, "min": 0, "max": 100, "unit": "RSI"},
            *_LIQUIDITY_PARAMS,
        ],
    },
    "darvas": {
        "scan_type": "darvas",
        "name": "Darvas Box",
        "description": "Box consolidation breakout with optional volume confirmation.",
        "core_criteria": [
            {
                "id": "darvas_box",
                "label": "Darvas box breakout",
                "detail": "Price breaks above a settled box top after consolidation.",
            },
            {
                "id": "fresh_breakout",
                "label": "Fresh upside breakout",
                "detail": "The box must end with an upside break within the recency window — stale or downside breaks are rejected.",
            },
            _LIQUIDITY_CRITERION,
        ],
        "param_schema": [
            {"id": "box_lookback", "label": "Box lookback (days)", "type": "number", "default": 120, "min": 30, "max": 250, "unit": "days"},
            {"id": "min_bars", "label": "Min history bars", "type": "number", "default": 60, "min": 20, "max": 120, "unit": "bars"},
            {"id": "settle_bars", "label": "Settlement bars", "type": "number", "default": 3, "min": 2, "max": 10, "unit": "bars"},
            {"id": "min_box_range_pct", "label": "Min box range", "type": "number", "default": 1.0, "min": 0.5, "max": 10, "unit": "%"},
            {"id": "max_box_range_pct", "label": "Max box range", "type": "number", "default": 15.0, "min": 5, "max": 30, "unit": "%"},
            {"id": "max_breakout_pct", "label": "Max breakout extension", "type": "number", "default": 10.0, "min": 2, "max": 25, "unit": "%"},
            {"id": "max_days_since_breakout", "label": "Breakout freshness", "type": "number", "default": 5, "min": 1, "max": 20, "unit": "bars"},
            {"id": "min_breakout_volume_multiple", "label": "Volume multiple", "type": "number", "default": 1.5, "min": 1, "max": 5, "unit": "×"},
            {"id": "require_volume_confirmation", "label": "Require volume confirmed", "type": "boolean", "default": False},
            {"id": "require_uptrend", "label": "Require Uptrend (Price > SMA50)", "type": "boolean", "default": True},
            *_LIQUIDITY_PARAMS,
        ],
    },
    "golden": {
        "scan_type": "golden",
        "name": "Golden Stocks",
        "description": "Price, revenue, and profit momentum with holdings quality ranking.",
        "core_criteria": [
            {
                "id": "price_momentum",
                "label": "Price momentum (YoY & QoQ)",
                "detail": "YoY and quarterly average price change must exceed your minimum thresholds.",
            },
            {
                "id": "financials_growing",
                "label": "Growing revenue & profit",
                "detail": "Quarterly and YoY revenue/profit growth with positive latest profit.",
            },
            {
                "id": "rank_score",
                "label": "Holdings quality rank",
                "detail": "Matches ranked by promoter/FII/DII and growth metrics.",
            },
            _LIQUIDITY_CRITERION,
        ],
        "param_schema": [
            {"id": "min_price_yoy_pct", "label": "Min price YoY", "type": "number", "default": 12, "min": -50, "max": 200, "unit": "%"},
            {"id": "min_price_qoq_pct", "label": "Min price QoQ", "type": "number", "default": 3, "min": -50, "max": 200, "unit": "%"},
            {"id": "require_revenue_growth", "label": "Require revenue growth", "type": "boolean", "default": True},
            {"id": "require_profit_growth", "label": "Require profit growth", "type": "boolean", "default": True},
            {"id": "min_revenue_growth_pct", "label": "Min revenue growth YoY", "type": "number", "default": 8, "min": 0, "max": 100, "unit": "%"},
            {"id": "min_profit_growth_pct", "label": "Min profit growth YoY", "type": "number", "default": 8, "min": 0, "max": 100, "unit": "%"},
            {"id": "max_distance_from_52w_high_pct", "label": "Max distance from 52w high", "type": "number", "default": 25, "min": 5, "max": 75, "unit": "%"},
            *_LIQUIDITY_PARAMS,
        ],
    },
    "mean_reversion": {
        "scan_type": "mean_reversion",
        "name": "Mean Reversion",
        "description": "Quality uptrends pulled back to oversold — built for choppy markets.",
        "core_criteria": [
            {
                "id": "uptrend_intact",
                "label": "Long-term uptrend intact",
                "detail": "Price above SMA200 so the dip is a pullback, not a downtrend.",
            },
            {
                "id": "oversold_dip",
                "label": "Oversold pullback",
                "detail": "RSI at/below your threshold and a meaningful dip off the 20-day high — but not a falling knife.",
            },
            {
                "id": "trade_plan",
                "label": "Snap-back trade plan",
                "detail": "Entry near current price, target the 20-day mean, stop an ATR multiple below — reward:risk shown per match.",
            },
            _LIQUIDITY_CRITERION,
        ],
        "param_schema": [
            {"id": "max_rsi", "label": "RSI oversold threshold", "type": "number", "default": 35, "min": 5, "max": 50, "unit": "RSI"},
            {"id": "min_pullback_pct", "label": "Min dip from 20d high", "type": "number", "default": 5, "min": 2, "max": 25, "unit": "%"},
            {"id": "max_pullback_pct", "label": "Max dip (avoid knives)", "type": "number", "default": 20, "min": 5, "max": 40, "unit": "%"},
            {"id": "require_above_sma200", "label": "Require long-term uptrend (Price > SMA200)", "type": "boolean", "default": True},
            {"id": "atr_stop_multiple", "label": "Stop distance (ATR ×)", "type": "number", "default": 1.5, "min": 0.5, "max": 4, "unit": "×"},
            {"id": "min_reward_risk", "label": "Min reward : risk", "type": "number", "default": 1, "min": 0.5, "max": 5, "unit": ":1"},
            *_LIQUIDITY_PARAMS,
        ],
    },
    "vol_squeeze": {
        "scan_type": "vol_squeeze",
        "name": "Volatility Squeeze",
        "description": "Tight ranges with contracting volatility — pre-breakout watchlist for sideways markets.",
        "core_criteria": [
            {
                "id": "tight_range",
                "label": "Tight trading range",
                "detail": "High–low range over the lookback window stays under your width limit, with price near the range top.",
            },
            {
                "id": "atr_contraction",
                "label": "Volatility contraction",
                "detail": "Current ATR well below its one-year average — coiling before expansion.",
            },
            {
                "id": "trade_plan",
                "label": "Range-expansion trade plan",
                "detail": "Entry on a break of the range high, measured-move target (range height added), stop at the range low.",
            },
            _LIQUIDITY_CRITERION,
        ],
        "param_schema": [
            {"id": "range_days", "label": "Range lookback", "type": "number", "default": 20, "min": 10, "max": 60, "unit": "days"},
            {"id": "max_range_pct", "label": "Max range width", "type": "number", "default": 8, "min": 3, "max": 20, "unit": "%"},
            {"id": "max_dist_from_range_high_pct", "label": "Max distance from range high", "type": "number", "default": 5, "min": 1, "max": 15, "unit": "%"},
            {"id": "max_atr_ratio", "label": "Max ATR vs 1y average", "type": "number", "default": 0.75, "min": 0.3, "max": 1, "unit": "×"},
            {"id": "require_volume_dryup", "label": "Require volume dry-up", "type": "boolean", "default": True},
            {"id": "max_volume_dryup_ratio", "label": "Max recent vs 50d volume", "type": "number", "default": 0.8, "min": 0.3, "max": 1.5, "unit": "×"},
            {"id": "require_above_sma200", "label": "Require long-term uptrend (Price > SMA200)", "type": "boolean", "default": False},
            *_LIQUIDITY_PARAMS,
        ],
    },
    "volume_surge": {
        "scan_type": "volume_surge",
        "name": "Volume Surge",
        "description": "Unusual accumulation — heavy volume with a strong up close.",
        "core_criteria": [
            {
                "id": "volume_spike",
                "label": "Volume multiple of normal",
                "detail": "Last session's volume is several times its 50-day average.",
            },
            {
                "id": "buyers_in_control",
                "label": "Buyers in control",
                "detail": "Price up on the day and closing in the upper part of the range — volume with intent.",
            },
            {
                "id": "trade_plan",
                "label": "Follow-through plan",
                "detail": "Watch signal: entry above the surge-day high, stop under the surge-day low.",
            },
            _LIQUIDITY_CRITERION,
        ],
        "param_schema": [
            {"id": "min_volume_multiple", "label": "Min volume vs 50d avg", "type": "number", "default": 3, "min": 1.5, "max": 10, "unit": "×"},
            {"id": "min_day_change_pct", "label": "Min day change", "type": "number", "default": 2, "min": 0, "max": 15, "unit": "%"},
            {"id": "min_close_strength_pct", "label": "Min close strength (of day range)", "type": "number", "default": 60, "min": 0, "max": 100, "unit": "%"},
            {"id": "require_uptrend", "label": "Require Uptrend (Price > SMA50)", "type": "boolean", "default": True},
            *_LIQUIDITY_PARAMS,
        ],
    },
    "weekly": {
        "scan_type": "weekly",
        "name": "Weekly Stocks",
        "description": "Weekly price momentum plus growing financials.",
        "core_criteria": [
            {
                "id": "weekly_price",
                "label": "Weekly price momentum",
                "detail": "YoY and 4-week price change must exceed your minimum thresholds.",
            },
            {
                "id": "weekly_trend",
                "label": "Weekly trend strength",
                "detail": "At least N of the last 4 weekly closes must be higher than the prior week.",
            },
            {
                "id": "financials_growing",
                "label": "Growing revenue & profit",
                "detail": "Same financial growth rules as Golden Stocks.",
            },
            _LIQUIDITY_CRITERION,
        ],
        "param_schema": [
            {"id": "min_price_yoy_pct", "label": "Min weekly YoY", "type": "number", "default": 12, "min": -50, "max": 200, "unit": "%"},
            {"id": "min_price_4w_pct", "label": "Min 4-week change", "type": "number", "default": 2, "min": -50, "max": 200, "unit": "%"},
            {"id": "min_weeks_up_in_4", "label": "Weeks up (of last 4)", "type": "number", "default": 3, "min": 1, "max": 4, "unit": "weeks"},
            {"id": "require_revenue_growth", "label": "Require revenue growth", "type": "boolean", "default": True},
            {"id": "require_profit_growth", "label": "Require profit growth", "type": "boolean", "default": True},
            {"id": "min_revenue_growth_pct", "label": "Min revenue growth YoY", "type": "number", "default": 8, "min": 0, "max": 100, "unit": "%"},
            {"id": "min_profit_growth_pct", "label": "Min profit growth YoY", "type": "number", "default": 8, "min": 0, "max": 100, "unit": "%"},
            {"id": "max_distance_from_52w_high_pct", "label": "Max distance from 52w high", "type": "number", "default": 25, "min": 5, "max": 75, "unit": "%"},
            *_LIQUIDITY_PARAMS,
        ],
    },
}


def get_scan_definition(scan_type: str) -> dict[str, Any] | None:
    return SCAN_DEFINITIONS.get(scan_type)


def list_scan_definitions() -> list[dict[str, Any]]:
    return list(SCAN_DEFINITIONS.values())


def default_params(scan_type: str) -> dict[str, Any]:
    """Factory defaults for UI — not persisted until user runs a scan."""
    defn = get_scan_definition(scan_type)
    if not defn:
        return {}
    out: dict[str, Any] = {}
    for field in defn.get("param_schema", []):
        out[field["id"]] = field.get("default")
    return out
