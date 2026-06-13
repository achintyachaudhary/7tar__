"""Company profile: market cap, sector, industry via yfinance."""

from __future__ import annotations

import logging

import yfinance as yf

from app.utils.network import without_proxy

logger = logging.getLogger(__name__)

# NSE-style market cap buckets (₹ Cr)
LARGE_CAP_MIN_CR = 20_000
MID_CAP_MIN_CR = 5_000


def _yf_symbol(symbol: str) -> str:
    symbol = symbol.upper()
    if not symbol.endswith((".NS", ".BO")):
        return f"{symbol}.NS"
    return symbol


def _to_crores(market_cap: float | None) -> float | None:
    if market_cap is None:
        return None
    return round(market_cap / 1e7, 2)


def _cap_category(market_cap_cr: float | None) -> str | None:
    if market_cap_cr is None:
        return None
    if market_cap_cr >= LARGE_CAP_MIN_CR:
        return "Large Cap"
    if market_cap_cr >= MID_CAP_MIN_CR:
        return "Mid Cap"
    return "Small Cap"


def get_company_profile(symbol: str) -> dict:
    yf_sym = _yf_symbol(symbol)
    out: dict = {
        "company_name": None,
        "sector": None,
        "industry": None,
        "market_cap_cr": None,
        "market_cap_category": None,
    }
    try:
        with without_proxy():
            info = yf.Ticker(yf_sym).info
        out["company_name"] = info.get("longName") or info.get("shortName")
        out["sector"] = info.get("sector")
        out["industry"] = info.get("industry")
        mc_cr = _to_crores(info.get("marketCap"))
        out["market_cap_cr"] = mc_cr
        out["market_cap_category"] = _cap_category(mc_cr)
    except Exception:
        logger.warning("Company profile fetch failed for %s", yf_sym)
    return out
