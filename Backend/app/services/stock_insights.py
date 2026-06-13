"""Combined shareholding + financial insights for stock detail modal.

Uses SQLite DB as a 90-day cache before falling back to live NSE/yfinance fetches.
"""

import logging

from app.db.database import SessionLocal
from app.db import crud
from app.db.models import FinancialCache
from app.services.company_profile import get_company_profile
from app.services.financials import get_financials
from app.services.holdings import get_shareholding_history, _normalize_shareholding_period
from app.services.scoring import compute_overall_score
from app.models import FinancialPeriod, ShareholdingPeriod, StockInsightsResponse

logger = logging.getLogger(__name__)


def get_stock_insights(symbol: str, force_refresh: bool = False) -> StockInsightsResponse:
    symbol = symbol.upper()
    if not symbol.endswith(".NS"):
        symbol = f"{symbol}.NS"

    nse_code = symbol.replace(".NS", "").replace(".BO", "")

    with SessionLocal() as db:
        # ── Profile ────────────────────────────────────────────────────────────
        if not force_refresh and crud.profile_is_fresh(db, symbol):
            prow = crud.get_profile(db, symbol)
            profile = {
                "company_name": prow.company_name,
                "sector": prow.sector,
                "industry": prow.industry,
                "market_cap_cr": prow.market_cap_cr,
                "market_cap_category": prow.cap_category,
            }
            last_profile = prow.last_updated.isoformat() if prow.last_updated else None
        else:
            profile = get_company_profile(symbol)
            crud.upsert_profile(db, symbol, {
                "company_name": profile.get("company_name"),
                "sector": profile.get("sector"),
                "industry": profile.get("industry"),
                "market_cap_cr": profile.get("market_cap_cr"),
                "cap_category": profile.get("market_cap_category"),
            })
            prow = crud.get_profile(db, symbol)
            last_profile = prow.last_updated.isoformat() if prow else None

        # ── Holdings ───────────────────────────────────────────────────────────
        if not force_refresh and crud.holdings_is_fresh(db, symbol):
            history_raw = [
                _normalize_shareholding_period(p)
                for p in crud.get_holdings_history(db, symbol)
            ]
            hrow = crud.get_holdings(db, symbol)
            last_holdings = hrow.last_fetched.isoformat() if hrow and hrow.last_fetched else None
        else:
            history_raw = get_shareholding_history(symbol, max_periods=5)
            latest_h = history_raw[0] if history_raw else {}
            crud.upsert_holdings(db, symbol, latest_h, history_raw)
            hrow = crud.get_holdings(db, symbol)
            last_holdings = hrow.last_fetched.isoformat() if hrow else None

        # ── Financials ─────────────────────────────────────────────────────────
        if not force_refresh and crud.financials_are_fresh(db, symbol):
            q_periods_raw = crud.get_financials_rows(db, symbol, is_quarterly=True)
            y_periods_raw = crud.get_financials_rows(db, symbol, is_quarterly=False)
            # Re-compute summary from cached rows
            financials_summary: dict = {}
            last_fin_row = (
                db.query(FinancialCache)
                .filter(FinancialCache.symbol == symbol)
                .order_by(FinancialCache.last_fetched.desc())
                .first()
            )
            last_financials = last_fin_row.last_fetched.isoformat() if last_fin_row else None
        else:
            financials = get_financials(symbol)
            q_periods_raw = financials.get("quarterly", [])
            y_periods_raw = financials.get("yearly", [])
            financials_summary = financials.get("summary", {})
            crud.upsert_financials(db, symbol, q_periods_raw, is_quarterly=True)
            crud.upsert_financials(db, symbol, y_periods_raw, is_quarterly=False)
            last_fin_row = (
                db.query(FinancialCache)
                .filter(FinancialCache.symbol == symbol)
                .order_by(FinancialCache.last_fetched.desc())
                .first()
            )
            last_financials = last_fin_row.last_fetched.isoformat() if last_fin_row else None

        # ── Compute overall score ──────────────────────────────────────────────
        retail_pct: float | None = None
        if history_raw:
            latest_h_for_score = history_raw[0]
            retail_pct = latest_h_for_score.get("retail_and_others_pct")

        # We don't have a live technical score here; retrieve from DB if stored
        prow2 = crud.get_profile(db, symbol)
        overall_score = prow2.overall_score if prow2 else None
        if overall_score is None and retail_pct is not None:
            overall_score = compute_overall_score(5, retail_pct)

    shareholding = [ShareholdingPeriod(**p) for p in history_raw]
    quarterly = [FinancialPeriod(**p) for p in q_periods_raw]
    yearly = [FinancialPeriod(**p) for p in y_periods_raw]

    company_name = profile.get("company_name") or nse_code

    return StockInsightsResponse(
        symbol=symbol,
        company_name=company_name,
        sector=profile.get("sector"),
        industry=profile.get("industry"),
        market_cap_cr=profile.get("market_cap_cr"),
        market_cap_category=profile.get("market_cap_category"),
        overall_score=overall_score,
        shareholding=shareholding,
        financials_quarterly=quarterly,
        financials_yearly=yearly,
        revenue_growth_yoy_pct=financials_summary.get("revenue", {}).get("yoy_pct") if financials_summary else None,
        revenue_cagr_3y_pct=financials_summary.get("revenue", {}).get("cagr_3y_pct") if financials_summary else None,
        profit_growth_yoy_pct=financials_summary.get("profit", {}).get("yoy_pct") if financials_summary else None,
        profit_cagr_3y_pct=financials_summary.get("profit", {}).get("cagr_3y_pct") if financials_summary else None,
        last_profile_updated=last_profile,
        last_holdings_updated=last_holdings,
        last_financials_updated=last_financials,
    )
