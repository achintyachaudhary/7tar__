"""₹1-lakh-per-IPO portfolio simulation across listing scenarios."""

from __future__ import annotations

from typing import Any

from app.db import crud
from app.db.database import SessionLocal
from app.services.ipo_catalog import _nse_rows_for_window

DEFAULT_INVESTMENT_INR = 100_000

SCENARIOS: list[dict[str, str]] = [
    {
        "id": "issue_to_listing_close",
        "label": "Buy at issue price → sell at listing-day close",
        "gain_field": "listing_day_gain_pct",
        "entry_label": "Issue price",
        "exit_label": "Listing-day close",
    },
    {
        "id": "issue_to_current",
        "label": "Buy at issue price → hold until today",
        "gain_field": "gain_vs_issue_pct",
        "entry_label": "Issue price",
        "exit_label": "Current price",
    },
    {
        "id": "listing_open_to_current",
        "label": "Buy at listing-day open → hold until today",
        "gain_field": "gain_listing_open_to_current_pct",
        "entry_label": "Listing-day open",
        "exit_label": "Current price",
    },
    {
        "id": "listing_close_to_current",
        "label": "Buy at listing-day close → hold until today",
        "gain_field": "gain_vs_listing_close_pct",
        "entry_label": "Listing-day close",
        "exit_label": "Current price",
    },
]


def _scenario_result(gain_pct: float | None, investment_inr: float) -> dict[str, Any] | None:
    if gain_pct is None:
        return None
    final_value = round(investment_inr * (1 + gain_pct / 100), 2)
    profit_inr = round(final_value - investment_inr, 2)
    return {
        "gain_pct": gain_pct,
        "final_value_inr": final_value,
        "profit_inr": profit_inr,
        "roi_pct": gain_pct,
    }


def _aggregate_scenario(
    rows: list[dict[str, Any]],
    scenario_id: str,
    gain_field: str,
    investment_inr: float,
) -> dict[str, Any]:
    included: list[dict[str, Any]] = []
    for row in rows:
        gain = row.get(gain_field)
        if gain is None:
            continue
        calc = _scenario_result(float(gain), investment_inr)
        if calc is None:
            continue
        included.append(
            {
                "symbol": row["symbol"],
                "listing_date": row["listing_date"],
                "company_name": row.get("company_name"),
                **calc,
            }
        )

    n = len(included)
    if n == 0:
        meta = next(s for s in SCENARIOS if s["id"] == scenario_id)
        return {
            "id": scenario_id,
            "label": meta["label"],
            "entry_label": meta["entry_label"],
            "exit_label": meta["exit_label"],
            "ipos_included": 0,
            "total_invested_inr": 0,
            "total_final_value_inr": 0,
            "total_profit_inr": 0,
            "portfolio_roi_pct": None,
            "winners": 0,
            "losers": 0,
            "avg_gain_pct": None,
            "best_ipo": None,
            "worst_ipo": None,
        }

    total_invested = investment_inr * n
    total_final = sum(r["final_value_inr"] for r in included)
    total_profit = round(total_final - total_invested, 2)
    portfolio_roi = round((total_profit / total_invested) * 100, 2) if total_invested else None
    winners = sum(1 for r in included if r["profit_inr"] > 0)
    avg_gain = round(sum(r["gain_pct"] for r in included) / n, 2)

    by_profit = sorted(included, key=lambda x: x["profit_inr"])
    best = by_profit[-1]
    worst = by_profit[0]

    meta = next(s for s in SCENARIOS if s["id"] == scenario_id)
    return {
        "id": scenario_id,
        "label": meta["label"],
        "entry_label": meta["entry_label"],
        "exit_label": meta["exit_label"],
        "ipos_included": n,
        "total_invested_inr": round(total_invested, 2),
        "total_final_value_inr": round(total_final, 2),
        "total_profit_inr": total_profit,
        "portfolio_roi_pct": portfolio_roi,
        "winners": winners,
        "losers": n - winners,
        "avg_gain_pct": avg_gain,
        "best_ipo": {
            "symbol": best["symbol"],
            "profit_inr": best["profit_inr"],
            "gain_pct": best["gain_pct"],
        },
        "worst_ipo": {
            "symbol": worst["symbol"],
            "profit_inr": worst["profit_inr"],
            "gain_pct": worst["gain_pct"],
        },
    }


def compute_portfolio_simulation(
    *,
    months: int | None = 6,
    investment_per_ipo_inr: float = DEFAULT_INVESTMENT_INR,
) -> dict[str, Any]:
    """
    If you invested `investment_per_ipo_inr` in each IPO under each scenario,
    what would total profit and portfolio ROI be?
    """
    symbols_filter = {r["symbol"] for r in _nse_rows_for_window(months)} if months else None
    ipo_rows: list[dict[str, Any]] = []

    with SessionLocal() as db:
        listings = crud.list_ipo_listings(db, symbols=symbols_filter)
        for row in listings:
            if row.market_status != "listed" or row.current_price is None:
                continue
            d = crud.ipo_listing_to_dict(row)
            ipo_rows.append(d)

    ipo_rows.sort(key=lambda x: x["listing_date"], reverse=True)

    scenario_summaries = [
        _aggregate_scenario(ipo_rows, s["id"], s["gain_field"], investment_per_ipo_inr)
        for s in SCENARIOS
    ]

    per_ipo: list[dict[str, Any]] = []
    for row in ipo_rows:
        scenarios_out: dict[str, Any] = {}
        for s in SCENARIOS:
            scenarios_out[s["id"]] = _scenario_result(
                row.get(s["gain_field"]),
                investment_per_ipo_inr,
            )
        per_ipo.append(
            {
                "symbol": row["symbol"],
                "company_name": row.get("company_name"),
                "listing_date": row["listing_date"],
                "issue_price": row.get("issue_price"),
                "listing_open": row.get("listing_open"),
                "listing_close": row.get("listing_close"),
                "current_price": row.get("current_price"),
                "scenarios": scenarios_out,
            }
        )

    return {
        "investment_per_ipo_inr": investment_per_ipo_inr,
        "months": months,
        "ipo_count": len(ipo_rows),
        "disclaimer": (
            "Hypothetical equal-weight simulation (₹1L per IPO). "
            "Ignores fees, taxes, lot size, and allotment. Not financial advice."
        ),
        "scenarios": scenario_summaries,
        "per_ipo": per_ipo,
    }
