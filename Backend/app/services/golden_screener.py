"""Golden Stock screener: price, revenue, and profit all growing QoQ and YoY (DB only)."""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from app.services.scan_context import symbol_meta
from app.services.scan_definitions import default_params
from app.services.scan_filters import (
    distance_from_52w_high_pct,
    liquidity_reject,
    reject as _reject,
)
from app.services.scan_fundamentals import load_quarterly_financials_db, load_shareholding_db
from app.services.scan_helpers import resample_weekly_df
from app.services.price_history import load_daily_history

logger = logging.getLogger(__name__)

TRADING_DAYS_QTR = 63
TRADING_DAYS_YEAR = 252


def _pct_change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None or previous == 0:
        return None
    return round(((current - previous) / abs(previous)) * 100, 2)


def _price_growth(df: pd.DataFrame) -> tuple[float | None, float | None]:
    if df is None or df.empty or len(df) < TRADING_DAYS_QTR + 10:
        return None, None
    closes = df["close"]
    current = float(closes.iloc[-1])
    yoy_idx = max(0, len(closes) - TRADING_DAYS_YEAR)
    yoy_base = float(closes.iloc[yoy_idx])
    yoy_pct = _pct_change(current, yoy_base)
    qoq_pct = None
    if len(closes) >= TRADING_DAYS_QTR * 2:
        recent = float(closes.iloc[-TRADING_DAYS_QTR:].mean())
        prior = float(closes.iloc[-TRADING_DAYS_QTR * 2 : -TRADING_DAYS_QTR].mean())
        qoq_pct = _pct_change(recent, prior)
    return yoy_pct, qoq_pct


def _financials_growing(
    q_periods: list[dict],
    *,
    require_revenue: bool = True,
    require_profit: bool = True,
    min_revenue_growth_pct: float = 0.0,
    min_profit_growth_pct: float = 0.0,
) -> tuple[bool, str | None, dict[str, float | None]]:
    """Returns (ok, fail_reason, growth summary).

    Rows at index -5 are four quarters back, i.e. the YoY comparison period.
    With fewer than five quarters of data, the prior quarter is the fallback base.
    """
    rev_rows = [p for p in q_periods if p.get("revenue_cr") is not None]
    prof_rows = [p for p in q_periods if p.get("profit_cr") is not None]
    if len(rev_rows) < 2 or len(prof_rows) < 2:
        return False, "fewer than 2 quarters of financials in DB", {}

    rev_yoy_base = rev_rows[-5]["revenue_cr"] if len(rev_rows) >= 5 else rev_rows[-2]["revenue_cr"]
    prof_yoy_base = prof_rows[-5]["profit_cr"] if len(prof_rows) >= 5 else prof_rows[-2]["profit_cr"]
    summary = {
        "revenue_growth_yoy_pct": _pct_change(rev_rows[-1]["revenue_cr"], rev_yoy_base),
        "profit_growth_yoy_pct": _pct_change(prof_rows[-1]["profit_cr"], prof_yoy_base),
    }

    if require_profit and (prof_rows[-1]["profit_cr"] or 0) <= 0:
        return False, "latest quarterly profit is not positive", summary

    if require_revenue:
        if rev_rows[-1]["revenue_cr"] <= rev_rows[-2]["revenue_cr"]:
            return False, "revenue fell QoQ", summary
        rev_growth = summary["revenue_growth_yoy_pct"]
        if rev_growth is None or rev_growth < min_revenue_growth_pct:
            return False, (
                f"revenue growth YoY {rev_growth if rev_growth is not None else 'n/a'}% "
                f"below {min_revenue_growth_pct:g}%"
            ), summary

    if require_profit:
        if prof_rows[-1]["profit_cr"] <= prof_rows[-2]["profit_cr"]:
            return False, "profit fell QoQ", summary
        prof_growth = summary["profit_growth_yoy_pct"]
        if prof_growth is None or prof_growth < min_profit_growth_pct:
            return False, (
                f"profit growth YoY {prof_growth if prof_growth is not None else 'n/a'}% "
                f"below {min_profit_growth_pct:g}%"
            ), summary

    return True, None, summary


def _weekly_price_growth(weekly: pd.DataFrame) -> tuple[float | None, float | None]:
    if len(weekly) < 5:
        return None, None
    closes = weekly["close"].to_numpy(dtype=float)
    current = closes[-1]
    four_week_idx = max(0, len(closes) - 5)
    four_week_pct = _pct_change(current, closes[four_week_idx])
    yoy_idx = max(0, len(closes) - 52)
    yoy_pct = _pct_change(current, closes[yoy_idx])
    return yoy_pct, four_week_pct


def _weekly_trend_ok(weekly: pd.DataFrame, min_up: int = 3) -> bool:
    if len(weekly) < 5:
        return False
    closes = weekly["close"].iloc[-5:].to_numpy(dtype=float)
    up_weeks = sum(1 for i in range(1, len(closes)) if closes[i] > closes[i - 1])
    return up_weeks >= min_up


def _calculate_holding_trends(shareholding: list[dict]) -> dict:
    if len(shareholding) < 2:
        return {
            "promoter_increasing": None,
            "fii_increasing": None,
            "dii_increasing": None,
            "mutual_fund_increasing": None,
        }

    latest = shareholding[-1]
    previous = shareholding[-2]

    def is_increasing(latest_val, prev_val):
        if latest_val is None or prev_val is None:
            return None
        return latest_val > prev_val

    return {
        "promoter_increasing": is_increasing(
            latest.get("promoter_holding_pct"),
            previous.get("promoter_holding_pct"),
        ),
        "fii_increasing": is_increasing(
            latest.get("fii_holding_pct"),
            previous.get("fii_holding_pct"),
        ),
        "dii_increasing": is_increasing(
            latest.get("dii_holding_pct"),
            previous.get("dii_holding_pct"),
        ),
        "mutual_fund_increasing": is_increasing(
            latest.get("mutual_fund_holding_pct"),
            previous.get("mutual_fund_holding_pct"),
        ),
    }


def _calculate_rank(stock_data: dict) -> float:
    score = 50.0

    promoter = stock_data.get("promoter_holding_pct")
    if promoter is not None:
        if promoter >= 50:
            score += 10
        elif promoter >= 30:
            score += 6
        elif promoter >= 15:
            score += 3

    if stock_data.get("shareholding"):
        latest_holding = stock_data["shareholding"][-1]
        retail = latest_holding.get("retail_and_others_pct")
        if retail is not None:
            if retail < 30:
                score += 10
            elif retail < 50:
                score += 5
            else:
                score -= 5

        fii = latest_holding.get("fii_holding_pct") or 0
        dii = latest_holding.get("dii_holding_pct") or 0
        institutional = fii + dii
        if institutional > 30:
            score += 10
        elif institutional > 15:
            score += 5

    rev_growth = stock_data.get("revenue_growth_yoy_pct")
    profit_growth = stock_data.get("profit_growth_yoy_pct")
    price_yoy = stock_data.get("price_yoy_pct")

    if rev_growth is not None:
        if rev_growth > 30:
            score += 15
        elif rev_growth > 15:
            score += 10
        elif rev_growth > 5:
            score += 5

    if profit_growth is not None:
        if profit_growth > 30:
            score += 15
        elif profit_growth > 15:
            score += 10
        elif profit_growth > 5:
            score += 5

    if price_yoy is not None:
        if price_yoy > 50:
            score += 10
        elif price_yoy > 25:
            score += 5

    return min(100.0, max(0.0, round(score, 1)))


def scan_golden_symbol(symbol: str, options: dict | None = None) -> dict | None:
    """Golden stock criteria — all inputs from DB."""
    opts = {**default_params("golden"), **(options or {})}
    min_yoy = float(opts.get("min_price_yoy_pct", 0))
    min_qoq = float(opts.get("min_price_qoq_pct", 0))
    require_revenue = bool(opts.get("require_revenue_growth", True))
    require_profit = bool(opts.get("require_profit_growth", True))
    max_52w_dist = float(opts.get("max_distance_from_52w_high_pct", 100) or 100)

    try:
        df = load_daily_history(symbol, period="1y", min_rows=TRADING_DAYS_QTR + 20)
        if df is None or df.empty:
            return _reject("insufficient daily history")

        liq_reason = liquidity_reject(
            df,
            min_price=float(opts.get("min_price", 0) or 0),
            min_avg_turnover_cr=float(opts.get("min_avg_turnover_cr", 0) or 0),
        )
        if liq_reason:
            return _reject(liq_reason)

        price_yoy_pct, price_qoq_pct = _price_growth(df)
        if price_yoy_pct is None or price_qoq_pct is None:
            return _reject("not enough history for YoY/QoQ price growth")
        if price_yoy_pct <= min_yoy:
            return _reject(f"price YoY {price_yoy_pct}% ≤ {min_yoy:g}% minimum")
        if price_qoq_pct <= min_qoq:
            return _reject(f"price QoQ {price_qoq_pct}% ≤ {min_qoq:g}% minimum")

        dist_52w = distance_from_52w_high_pct(df)
        if dist_52w is not None and dist_52w > max_52w_dist:
            return _reject(
                f"{dist_52w:.1f}% below 52w high (max {max_52w_dist:g}%) — momentum faded"
            )

        weekly = resample_weekly_df(df)
        if len(weekly) < 8:
            return _reject(f"only {len(weekly)} weekly bars (need 8+)")

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
        current_close = round(float(df["close"].iloc[-1]), 2)

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

        result = {
            "symbol": symbol.upper() if symbol.upper().endswith((".NS", ".BO")) else f"{symbol.upper()}.NS",
            "company_name": meta["company_name"],
            "industry": meta["industry"],
            "market_cap_cr": meta["market_cap_cr"],
            "market_cap_category": meta["market_cap_category"],
            "price": current_close,
            "price_yoy_pct": price_yoy_pct,
            "price_qoq_pct": price_qoq_pct,
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
        logger.exception("Golden scan failed for %s", symbol)
        return None
