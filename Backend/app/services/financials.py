"""Company financial statements — vendor-routed (Upstox first, yfinance fallback)."""

from __future__ import annotations

import logging
import re
from datetime import datetime

import yfinance as yf

from app.utils.network import without_proxy

logger = logging.getLogger(__name__)

REVENUE_ROWS = ("Total Revenue", "Operating Revenue")
PROFIT_ROWS = ("Net Income Common Stockholders", "Net Income")

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_QUARTER_END_DAY = {3: 31, 6: 30, 9: 30, 12: 31}


def _yf_symbol(symbol: str) -> str:
    symbol = symbol.upper()
    if not symbol.endswith((".NS", ".BO")):
        return f"{symbol}.NS"
    return symbol


def _period_label(dt: datetime, yearly: bool) -> str:
    if yearly:
        return str(dt.year)
    return dt.strftime("%b '%y")


def _to_crores(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value / 1e7, 2)


def _pick_row(df, names: tuple[str, ...]):
    for name in names:
        if name in df.index:
            return df.loc[name]
    return None


def _series_to_periods(series, yearly: bool) -> list[dict]:
    if series is None:
        return []

    items: list[dict] = []
    for col in series.index:
        val = series[col]
        if val is None or (hasattr(val, "__float__") and str(val) == "nan"):
            continue
        try:
            num = float(val)
        except (TypeError, ValueError):
            continue
        if num == 0:
            continue
        dt = col.to_pydatetime() if hasattr(col, "to_pydatetime") else col
        items.append(
            {
                "period": dt.strftime("%Y-%m-%d"),
                "label": _period_label(dt, yearly),
                "value_cr": _to_crores(num),
            },
        )

    items.sort(key=lambda x: x["period"])
    return items[-8:] if yearly else items[-8:]


def _pct_change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None or previous == 0:
        return None
    return round(((current - previous) / abs(previous)) * 100, 2)


def _growth_summary(periods: list[dict]) -> dict[str, float | None]:
    if len(periods) < 2:
        return {"yoy_pct": None, "cagr_3y_pct": None}

    latest = periods[-1]["value_cr"]
    prev = periods[-2]["value_cr"]
    yoy = _pct_change(latest, prev)

    cagr = None
    if len(periods) >= 4:
        start = periods[-4]["value_cr"]
        if start and start > 0 and latest is not None and latest > 0:
            try:
                cagr = round(((latest / start) ** (1 / 3) - 1) * 100, 2)
            except (ValueError, TypeError):
                # Handle cases where calculation results in complex numbers or other errors
                cagr = None

    return {"yoy_pct": yoy, "cagr_3y_pct": cagr}


def _upstox_period_to_date(period: str) -> tuple[str, str] | None:
    """'Mar 2026' → ('2026-03-31', "Mar '26"); '2026' → ('2026-12-31', '2026')."""
    period = (period or "").strip()
    m = re.match(r"([A-Za-z]{3})\w*\s+(\d{4})", period)
    if m:
        month = _MONTHS.get(m.group(1).lower())
        year = int(m.group(2))
        if month:
            day = _QUARTER_END_DAY.get(month, 28)
            return f"{year:04d}-{month:02d}-{day:02d}", f"{m.group(1).title()} '{str(year)[2:]}"
    if re.fullmatch(r"\d{4}", period):
        return f"{period}-12-31", period
    return None


def _upstox_statement_to_periods(
    statement: list[dict], *, yearly: bool
) -> list[dict]:
    """Upstox income_statement categories → merged [{period, label, revenue_cr, profit_cr}]."""
    by_category: dict[str, dict[str, float]] = {}
    for row in statement:
        cat = row.get("category")
        if cat not in ("revenue", "net_profit"):
            continue
        for item in row.get("history") or []:
            parsed = _upstox_period_to_date(str(item.get("period") or ""))
            if parsed is None or item.get("value") is None:
                continue
            period_date, _label = parsed
            by_category.setdefault(period_date, {})[cat] = float(item["value"])

    merged: list[dict] = []
    for period_date in sorted(by_category):
        vals = by_category[period_date]
        if "revenue" not in vals:
            continue
        dt = datetime.strptime(period_date, "%Y-%m-%d")
        merged.append(
            {
                "period": period_date,
                "label": _period_label(dt, yearly),
                "revenue_cr": round(vals["revenue"], 2),
                "profit_cr": round(vals["net_profit"], 2) if "net_profit" in vals else None,
            }
        )
    return merged[-8:]


def _get_financials_upstox(symbol: str) -> dict | None:
    """Income statements from the Upstox Analytics API (values already in Cr)."""
    from app.services.vendors import upstox

    isin = upstox.resolve_isin(symbol)
    if not isin:
        logger.info("No ISIN for %s in Upstox instrument master", symbol)
        return None

    quarterly = _upstox_statement_to_periods(
        upstox.fetch_income_statement(isin, time_period="quarterly"), yearly=False
    )
    yearly = _upstox_statement_to_periods(
        upstox.fetch_income_statement(isin, time_period="yearly"), yearly=True
    )
    if not quarterly and not yearly:
        return None

    return {
        "quarterly": quarterly,
        "yearly": yearly,
        "summary": {
            "revenue": _growth_summary(
                [{"value_cr": p["revenue_cr"]} for p in quarterly if p.get("revenue_cr")]
            ),
            "profit": _growth_summary(
                [{"value_cr": p["profit_cr"]} for p in quarterly if p.get("profit_cr")]
            ),
        },
        "source": "upstox",
    }


def get_financials(symbol: str) -> dict:
    from app.services.vendors.registry import use_upstox

    if use_upstox("fundamentals"):
        try:
            result = _get_financials_upstox(symbol)
            if result is not None:
                return result
        except Exception:
            logger.exception("Upstox financials failed for %s — falling back to yfinance", symbol)

    yf_sym = _yf_symbol(symbol)
    try:
        with without_proxy():
            ticker = yf.Ticker(yf_sym)
            quarterly = ticker.quarterly_income_stmt
            annual = ticker.income_stmt
    except Exception:
        logger.exception("Financial fetch failed for %s", symbol)
        return {"quarterly": [], "yearly": [], "summary": {}}

    q_rev = _series_to_periods(_pick_row(quarterly, REVENUE_ROWS), yearly=False)
    q_profit = _series_to_periods(_pick_row(quarterly, PROFIT_ROWS), yearly=False)
    y_rev = _series_to_periods(_pick_row(annual, REVENUE_ROWS), yearly=True)
    y_profit = _series_to_periods(_pick_row(annual, PROFIT_ROWS), yearly=True)

    def merge(rev_list: list[dict], profit_list: list[dict]) -> list[dict]:
        profit_by_period = {p["period"]: p["value_cr"] for p in profit_list}
        merged = []
        for r in rev_list:
            merged.append(
                {
                    "period": r["period"],
                    "label": r["label"],
                    "revenue_cr": r["value_cr"],
                    "profit_cr": profit_by_period.get(r["period"]),
                },
            )
        return merged

    quarterly_merged = merge(q_rev, q_profit)
    yearly_merged = merge(y_rev, y_profit)

    return {
        "quarterly": quarterly_merged,
        "yearly": yearly_merged,
        "summary": {
            "revenue": _growth_summary([{"value_cr": p["revenue_cr"]} for p in quarterly_merged if p.get("revenue_cr")]),
            "profit": _growth_summary([{"value_cr": p["profit_cr"]} for p in quarterly_merged if p.get("profit_cr")]),
        },
        "source": "yfinance",
    }
