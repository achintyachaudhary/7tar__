"""Shared IPO catalog: NSE listings + Yahoo prices + ML features (one DB for Tracker & Research)."""

from __future__ import annotations

import json
import logging
import math
import os
import time
from datetime import datetime, timezone
from typing import Any

from app.db import crud
from app.db.database import SessionLocal
from app.schemas.ipo_llm import IpoBatchFetchItem
from app.services.ipo_fetcher import fetch_all_past_ipos, filter_all_equity_ipos
from app.services.ipo_llm_research import batch_fetch_ipo_research
from app.services.ipo_performance import enrich_ipos_parallel
from app.services.ipo_research.market_features import market_features_at_listing

logger = logging.getLogger(__name__)

# Default window aligned with IPO Tracker (2 months); prepare can pass months=None for all since 2018.
DEFAULT_TRACKER_MONTHS = 2


def _empty_subscription_features() -> dict[str, Any]:
    return {
        "has_subscription_data": 0,
        "overall_times_subscribed": None,
        "overall_times_subscribed_log": None,
        "qib_times_subscribed": None,
        "nii_times_subscribed": None,
        "retail_times_subscribed": None,
        "employee_times_subscribed": None,
        "qib_to_retail_ratio": None,
    }


def _subscription_features(symbol: str) -> dict[str, Any]:
    """Investor subscription multiples (from shared ipo_llm_research / Gemini)."""
    with SessionLocal() as db:
        row = crud.get_ipo_llm_research(db, symbol)
    if row is None or (row.status or "") != "fetched":
        return _empty_subscription_features()
    try:
        payload = json.loads(row.payload_json)
        sub = payload.get("subscription_summary") or {}
        cats = sub.get("category_breakdown") or {}

        def _times(key: str) -> float | None:
            cat = cats.get(key) or {}
            v = cat.get("times_subscribed")
            return float(v) if v is not None else None

        overall_raw = sub.get("overall_times_subscribed")
        overall = float(overall_raw) if overall_raw is not None else None
        qib = _times("qualified_institutional_buyers_qib")
        retail = _times("retail_individual_investors_rii")
        ratio = (
            round(qib / retail, 4)
            if qib is not None and retail is not None and retail > 0
            else None
        )
        if overall is None and qib is None and retail is None:
            return _empty_subscription_features()

        return {
            "has_subscription_data": 1,
            "overall_times_subscribed": overall,
            "overall_times_subscribed_log": (
                round(math.log1p(overall), 4) if overall is not None and overall >= 0 else None
            ),
            "qib_times_subscribed": qib,
            "nii_times_subscribed": _times("non_institutional_investors_nii"),
            "retail_times_subscribed": retail,
            "employee_times_subscribed": _times("employee_reservation"),
            "qib_to_retail_ratio": ratio,
        }
    except (json.JSONDecodeError, TypeError, ValueError):
        return _empty_subscription_features()


def _count_with_subscription(months: int | None) -> int:
    symbols = {r["symbol"] for r in _nse_rows_for_window(months)}
    count = 0
    for sym in symbols:
        sub = _subscription_features(sym)
        if sub.get("has_subscription_data") == 1 and sub.get("overall_times_subscribed") is not None:
            count += 1
    return count


def _count_subscription_pending(months: int | None, *, force: bool = False) -> int:
    if not os.getenv("GEMINI_API_KEY"):
        return 0
    nse_rows = _nse_rows_for_window(months)
    pending = 0
    with SessionLocal() as db:
        for row in nse_rows:
            sym = row["symbol"]
            llm = crud.get_ipo_llm_research(db, sym)
            if force or llm is None or (llm.status or "") != "fetched":
                pending += 1
    return pending


def sync_subscription_for_catalog(
    *,
    months: int | None = DEFAULT_TRACKER_MONTHS,
    batch_size: int = 8,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """
    Fetch missing IPO subscription times via LLM into ipo_llm_research (shared with Tracker).
    """
    if not os.getenv("GEMINI_API_KEY"):
        return {
            "subscription_skipped": True,
            "subscription_skip_reason": "GEMINI_API_KEY not set in Backend/.env",
            "subscription_fetched": 0,
            "subscription_failed": 0,
            "subscription_pending": _count_subscription_pending(months),
            "with_subscription_data": _count_with_subscription(months),
        }

    nse_rows = _nse_rows_for_window(months)
    to_fetch: list[IpoBatchFetchItem] = []
    with SessionLocal() as db:
        for row in nse_rows:
            sym = row["symbol"]
            llm = crud.get_ipo_llm_research(db, sym)
            if force_refresh or llm is None or (llm.status or "") != "fetched":
                to_fetch.append(
                    IpoBatchFetchItem(
                        symbol=sym,
                        company_name=row.get("company_name"),
                    ),
                )

    batch = to_fetch[:batch_size]
    fetched = failed = skipped = 0
    if batch:
        time.sleep(0.8)
        resp = batch_fetch_ipo_research(batch, skip_fetched=not force_refresh)
        fetched = resp.fetched_count
        failed = resp.failed_count
        skipped = resp.skipped_count

    pending = _count_subscription_pending(months, force=False)
    return {
        "subscription_skipped": False,
        "subscription_fetched": fetched,
        "subscription_failed": failed,
        "subscription_cached": skipped,
        "subscription_pending": pending,
        "with_subscription_data": _count_with_subscription(months),
    }


def _targets_from_row(row: dict) -> dict[str, Any]:
    ld = row.get("listing_day_gain_pct")
    gi = row.get("gain_vs_issue_pct")
    gl = row.get("gain_listing_open_to_current_pct")
    return {
        "profit_listing_day": 1 if ld is not None and ld > 0 else 0 if ld is not None else None,
        "profit_vs_issue": 1 if gi is not None and gi > 0 else 0 if gi is not None else None,
        "strong_profit_vs_issue": 1 if gi is not None and gi >= 15 else 0 if gi is not None else None,
        "profit_buy_listing_open": 1 if gl is not None and gl > 0 else 0 if gl is not None else None,
        "listing_day_gain_pct": ld,
        "gain_vs_issue_pct": gi,
        "gain_listing_open_to_current_pct": gl,
    }


def _features_from_row(row: dict, market: dict[str, Any], sub: dict[str, Any]) -> dict[str, Any]:
    is_sme = 1 if (row.get("security_type") or "").upper() == "SME" else 0
    issue_price = row.get("issue_price")
    return {
        "symbol": row["symbol"],
        "listing_date": row["listing_date"],
        "security_type_sme": is_sme,
        "issue_price": issue_price,
        "issue_price_log": (
            float(math.log(issue_price)) if issue_price and issue_price > 0 else None
        ),
        **market,
        **{k: v for k, v in sub.items() if k != "has_subscription_data"},
        "has_subscription_data": sub.get("has_subscription_data", 0),
    }


def _nse_rows_for_window(months: int | None) -> list[dict]:
    raw = fetch_all_past_ipos()
    if months is None:
        return filter_all_equity_ipos(raw)
    return filter_all_equity_ipos(raw, months_back=months)


def _enriched_to_db_fields(enriched: dict) -> dict[str, Any]:
    status = enriched.get("status") or "listed"
    return {
        "company_name": enriched.get("company_name"),
        "security_type": enriched.get("security_type") or "",
        "ipo_start_date": enriched.get("ipo_start_date") or "",
        "ipo_end_date": enriched.get("ipo_end_date") or "",
        "listing_date": enriched["listing_date"],
        "listing_date_display": enriched.get("listing_date_display") or "",
        "issue_price": enriched.get("issue_price"),
        "price_range": enriched.get("price_range") or "",
        "yf_symbol": enriched.get("yf_symbol"),
        "listing_open": enriched.get("listing_open"),
        "listing_close": enriched.get("listing_close"),
        "listing_high": enriched.get("listing_high"),
        "current_price": enriched.get("current_price"),
        "listing_day_gain_pct": enriched.get("listing_day_gain_pct"),
        "gain_vs_issue_pct": enriched.get("gain_vs_issue_pct"),
        "gain_vs_listing_close_pct": enriched.get("gain_vs_listing_close_pct"),
        "gain_listing_open_to_current_pct": enriched.get("gain_listing_open_to_current_pct"),
        "market_status": status,
    }


def sync_ipo_catalog(
    *,
    months: int | None = DEFAULT_TRACKER_MONTHS,
    force_refresh: bool = False,
    batch_size: int = 40,
) -> dict[str, Any]:
    """
    Upsert NSE IPO rows and fetch Yahoo prices into shared ipo_listings table.
    Used by IPO Tracker (refresh) and IPO Research (prepare).
    """
    nse_rows = _nse_rows_for_window(months)
    to_enrich: list[dict] = []
    skipped_cached = 0

    with SessionLocal() as db:
        for row in nse_rows:
            existing = crud.get_ipo_listing(db, row["symbol"])
            if existing and not force_refresh:
                if existing.market_status == "no_market_data":
                    skipped_cached += 1
                    continue
                if existing.market_status == "listed" and existing.current_price is not None:
                    skipped_cached += 1
                    continue
            to_enrich.append(row)

    if batch_size > 0 and len(to_enrich) > batch_size:
        batch = to_enrich[:batch_size]
    else:
        batch = to_enrich

    enriched_batch = enrich_ipos_parallel(batch) if batch else []
    now = datetime.now(timezone.utc)
    listed_count = 0
    no_data_count = 0

    with SessionLocal() as db:
        for enriched in enriched_batch:
            fields = _enriched_to_db_fields(enriched)
            ml_status = "pending"
            if fields["market_status"] == "no_market_data":
                ml_status = "no_market_data"
                no_data_count += 1
            else:
                listed_count += 1
            crud.upsert_ipo_listing(
                db,
                symbol=enriched["symbol"],
                price_fetched_at=now,
                ml_status=ml_status,
                **fields,
            )

        batch_symbols = {r["symbol"] for r in batch}
        for row in nse_rows:
            if row["symbol"] in batch_symbols:
                continue
            if crud.get_ipo_listing(db, row["symbol"]) is None:
                crud.upsert_ipo_listing(
                    db,
                    symbol=row["symbol"],
                    company_name=row.get("company_name"),
                    security_type=row.get("security_type") or "",
                    ipo_start_date=row.get("ipo_start_date") or "",
                    ipo_end_date=row.get("ipo_end_date") or "",
                    listing_date=row["listing_date"],
                    listing_date_display=row.get("listing_date_display") or "",
                    issue_price=row.get("issue_price"),
                    price_range=row.get("price_range") or "",
                    market_status="pending",
                    ml_status="pending",
                )

    pending = _count_pending_prices(months)
    stats = _catalog_stats(months)

    return {
        "months": months,
        "total_nse_ipos": len(nse_rows),
        "newly_enriched": len(enriched_batch),
        "newly_listed": listed_count,
        "skipped_cached": skipped_cached,
        "no_market_data": no_data_count,
        "pending_remaining": pending,
        **stats,
    }


def _count_pending_prices(months: int | None) -> int:
    nse_rows = _nse_rows_for_window(months)
    symbols = {r["symbol"] for r in nse_rows}
    with SessionLocal() as db:
        by_sym = {r.symbol: r for r in crud.list_ipo_listings(db, symbols=symbols)}
    pending = 0
    for row in nse_rows:
        rec = by_sym.get(row["symbol"])
        if rec is None:
            pending += 1
            continue
        if rec.market_status == "no_market_data":
            continue
        if rec.market_status != "listed" or rec.current_price is None:
            pending += 1
    return pending


def _catalog_stats(months: int | None = None) -> dict[str, int]:
    nse_rows = _nse_rows_for_window(months)
    symbols = {r["symbol"] for r in nse_rows}
    with SessionLocal() as db:
        rows = crud.list_ipo_listings(db, symbols=symbols)
    by_sym = {r.symbol: r for r in rows}
    with_prices = sum(
        1 for r in by_sym.values() if r.market_status == "listed" and r.current_price
    )
    ml_ready = sum(1 for r in by_sym.values() if r.ml_status == "ready")
    no_data = sum(1 for r in by_sym.values() if r.market_status == "no_market_data")
    with_sub = sum(
        1
        for sym in symbols
        if (_subscription_features(sym).get("has_subscription_data") == 1)
    )
    return {
        "nse_universe": len(nse_rows),
        "catalog_total": len(symbols),
        "with_market_data": with_prices,
        "with_subscription_data": with_sub,
        "ml_ready": ml_ready,
        "no_market_data": no_data,
        "total_dataset_rows": ml_ready,
    }


def list_ipo_listings_for_api(months: int = 2) -> list[dict[str, Any]]:
    """Rows for IPO Tracker API (same shape as enrich_ipos_parallel output)."""
    cutoff = None
    if months:
        from datetime import timedelta

        cutoff = (datetime.now() - timedelta(days=months * 30)).strftime("%Y-%m-%d")

    with SessionLocal() as db:
        rows = crud.list_ipo_listings(db)
    out: list[dict[str, Any]] = []
    for r in rows:
        if cutoff and r.listing_date < cutoff:
            continue
        out.append(crud.ipo_listing_to_dict(r))
    out.sort(key=lambda x: x["listing_date"], reverse=True)
    return out


def build_ml_features_for_catalog(
    *,
    months: int | None = DEFAULT_TRACKER_MONTHS,
    force: bool = False,
) -> dict[str, Any]:
    """Compute ML features for every IPO in catalog that has Yahoo price data."""
    from app.services.market_indices import ensure_market_indices_refreshed

    ensure_market_indices_refreshed()
    symbols_filter = {r["symbol"] for r in _nse_rows_for_window(months)} if months else None
    built = 0
    skipped = 0
    now = datetime.now(timezone.utc)

    with SessionLocal() as db:
        rows = crud.list_ipo_listings(db, symbols=symbols_filter)
        for row in rows:
            sym = row.symbol
            if row.market_status != "listed" or row.current_price is None:
                crud.upsert_ipo_listing(db, sym, ml_status="no_market_data")
                skipped += 1
                continue
            if row.ml_status == "ready" and not force:
                built += 1
                continue

            d = crud.ipo_listing_to_dict(row)
            market = market_features_at_listing(d["listing_date"])
            sub = _subscription_features(d["symbol"])
            targets = _targets_from_row(d)
            features = _features_from_row(d, market, sub)
            crud.upsert_ipo_listing(
                db,
                sym,
                features_json=json.dumps(features),
                targets_json=json.dumps(targets),
                ml_status="ready",
                ml_built_at=now,
            )
            built += 1

    stats = _catalog_stats(months)
    return {
        "months": months,
        "ml_built": built,
        "skipped_no_price": skipped,
        **stats,
    }


def load_ml_dataframe():
    import pandas as pd

    rows = []
    with SessionLocal() as db:
        for row in crud.list_ipo_listings(db, ml_ready_only=True):
            feats = json.loads(row.features_json or "{}")
            tgts = json.loads(row.targets_json or "{}")
            if tgts.get("skipped"):
                continue
            rows.append({**feats, **{f"target_{k}": v for k, v in tgts.items()}})

    return pd.DataFrame(rows) if rows else pd.DataFrame()


def dataset_stats(months: int | None = DEFAULT_TRACKER_MONTHS) -> dict[str, Any]:
    stats = _catalog_stats(months=months)
    pending = _count_pending_prices(months)
    with SessionLocal() as db:
        latest = crud.latest_ipo_listing_update(db)

    with_prices = stats["with_market_data"]
    ml_ready = stats["ml_ready"]
    return {
        "total_rows": ml_ready,
        "nse_universe": stats["nse_universe"],
        "catalog_total": stats["catalog_total"],
        "with_market_data": with_prices,
        "with_subscription_data": stats.get("with_subscription_data", 0),
        "subscription_pending": _count_subscription_pending(months),
        "no_market_data": stats["no_market_data"],
        "ml_ready": ml_ready,
        "ml_ready_matches_prices": ml_ready == with_prices,
        "universe_size": stats["nse_universe"],
        "months_back": months if months is not None else 0,
        "pending": pending,
        "latest_built_at": latest.isoformat() if latest else None,
        "min_rows_for_ml": 30,
        "ready_for_ml": ml_ready >= 30,
    }
