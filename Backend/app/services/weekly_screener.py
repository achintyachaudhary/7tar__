"""Weekly Stock screener: weekly price momentum + growing financials (DB only)."""

from __future__ import annotations

import logging
from typing import Any

from app.services.golden_screener import (
    _calculate_holding_trends,
    _calculate_rank,
    _financials_growing,
    _price_growth,
    _weekly_price_growth,
    _weekly_trend_ok,
)
from app.services.price_history import load_daily_history
from app.services.scan_context import symbol_meta
from app.services.scan_definitions import default_params
from app.services.scan_filters import (
    distance_from_52w_high_pct,
    liquidity_reject,
    reject as _reject,
)
from app.services.scan_fundamentals import load_quarterly_financials_db, load_shareholding_db
from app.services.scan_helpers import resample_weekly_df

logger = logging.getLogger(__name__)

MIN_WEEKLY_BARS = 12
TRADING_DAYS_QTR = 63


def scan_weekly_symbol(symbol: str, options: dict | None = None) -> dict | None:
    """
    Weekly stock criteria — daily DB first for fast rejection, then weekly resample.
    """
    opts = {**default_params("weekly"), **(options or {})}
    min_yoy = float(opts.get("min_price_yoy_pct", 0))
    min_4w = float(opts.get("min_price_4w_pct", 0))
    min_weeks_up = int(opts.get("min_weeks_up_in_4", 3))
    require_revenue = bool(opts.get("require_revenue_growth", True))
    require_profit = bool(opts.get("require_profit_growth", True))
    max_52w_dist = float(opts.get("max_distance_from_52w_high_pct", 100) or 100)

    try:
        daily = load_daily_history(symbol, period="1y", min_rows=TRADING_DAYS_QTR + 20)
        if daily is None or daily.empty:
            return _reject("insufficient daily history")

        liq_reason = liquidity_reject(
            daily,
            min_price=float(opts.get("min_price", 0) or 0),
            min_avg_turnover_cr=float(opts.get("min_avg_turnover_cr", 0) or 0),
        )
        if liq_reason:
            return _reject(liq_reason)

        # Fast daily price rejection before heavier weekly / financials work
        daily_yoy, _ = _price_growth(daily)
        if daily_yoy is not None and daily_yoy <= min_yoy:
            return _reject(f"price YoY {daily_yoy}% ≤ {min_yoy:g}% minimum")

        weekly = resample_weekly_df(daily)
        if len(weekly) < MIN_WEEKLY_BARS:
            return _reject(f"only {len(weekly)} weekly bars (need {MIN_WEEKLY_BARS}+)")

        price_yoy_pct, price_4w_pct = _weekly_price_growth(weekly)
        if price_yoy_pct is None or price_4w_pct is None:
            return _reject("not enough weekly history for YoY/4-week growth")
        if price_yoy_pct <= min_yoy:
            return _reject(f"weekly YoY {price_yoy_pct}% ≤ {min_yoy:g}% minimum")
        if price_4w_pct <= min_4w:
            return _reject(f"4-week change {price_4w_pct}% ≤ {min_4w:g}% minimum")
        if not _weekly_trend_ok(weekly, min_up=min_weeks_up):
            return _reject(f"fewer than {min_weeks_up} of last 4 weeks closed higher")

        dist_52w = distance_from_52w_high_pct(daily)
        if dist_52w is not None and dist_52w > max_52w_dist:
            return _reject(
                f"{dist_52w:.1f}% below 52w high (max {max_52w_dist:g}%) — momentum faded"
            )

        q_periods = load_quarterly_financials_db(symbol)
        fin_ok, fin_reason, fin_summary = _financials_growing(
            q_periods,
            require_revenue=require_revenue,
            require_profit=require_profit,
            min_revenue_growth_pct=float(opts.get("min_revenue_growth_pct", 0) or 0),
            min_profit_growth_pct=float(opts.get("min_profit_growth_pct", 0) or 0),
        )
        if (require_revenue or require_profit) and not fin_ok:
            return _reject(fin_reason or "financials not growing")

        shareholding = load_shareholding_db(symbol)
        meta = symbol_meta(symbol)
        current_close = round(float(weekly["close"].iloc[-1]), 2)

        promoter_pct = None
        fii_pct = None
        dii_pct = None
        retail_pct = None
        mutual_fund_pct = None

        if shareholding:
            latest = shareholding[-1]
            promoter_pct = latest.get("promoter_holding_pct")
            fii_pct = latest.get("fii_holding_pct")
            dii_pct = latest.get("dii_holding_pct")
            retail_pct = latest.get("retail_and_others_pct")
            mutual_fund_pct = latest.get("mutual_fund_holding_pct")

        holding_trends = _calculate_holding_trends(shareholding)

        result: dict[str, Any] = {
            "symbol": symbol.upper() if symbol.upper().endswith((".NS", ".BO")) else f"{symbol.upper()}.NS",
            "company_name": meta["company_name"],
            "industry": meta["industry"],
            "market_cap_cr": meta["market_cap_cr"],
            "market_cap_category": meta["market_cap_category"],
            "price": current_close,
            "price_yoy_pct": price_yoy_pct,
            "price_qoq_pct": price_4w_pct,
            "distance_from_52w_high_pct": round(dist_52w, 2) if dist_52w is not None else None,
            "revenue_growth_yoy_pct": fin_summary.get("revenue_growth_yoy_pct"),
            "profit_growth_yoy_pct": fin_summary.get("profit_growth_yoy_pct"),
            "promoter_holding_pct": promoter_pct,
            "fii_holding_pct": fii_pct,
            "dii_holding_pct": dii_pct,
            "retail_holding_pct": retail_pct,
            "mutual_fund_holding_pct": mutual_fund_pct,
            "promoter_increasing": holding_trends["promoter_increasing"],
            "fii_increasing": holding_trends["fii_increasing"],
            "dii_increasing": holding_trends["dii_increasing"],
            "mutual_fund_increasing": holding_trends["mutual_fund_increasing"],
            "financials_quarterly": q_periods[-8:],
            "financials_yearly": [],
            "shareholding": shareholding,
        }

        result["rank_score"] = _calculate_rank(result)
        return result
    except Exception:
        logger.exception("Weekly scan failed for %s", symbol)
        return None
