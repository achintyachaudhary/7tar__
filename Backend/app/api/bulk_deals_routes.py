"""API routes for bulk deals data."""

from __future__ import annotations

from fastapi import APIRouter

from app.db import crud
from app.db.database import SessionLocal
from app.services.bulk_deals import (
    build_client_analytics,
    enrich_bulk_deals,
    fetch_and_store_bulk_deals,
)

bulk_deals_router = APIRouter(prefix="/api/bulk-deals", tags=["bulk-deals"])


@bulk_deals_router.get("")
def get_bulk_deals(date: str | None = None, limit: int = 500):
    """Get bulk deals with amount, market cap, and deal-date 1D % change."""
    with SessionLocal() as db:
        deals = crud.list_bulk_deals(db, deal_date=date, limit=limit)

    return enrich_bulk_deals(deals)


@bulk_deals_router.get("/analytics")
def get_bulk_deals_analytics(limit: int = 10000):
    """Client-centric analytics: ALL deals grouped by client and stock, sorted by volume."""
    with SessionLocal() as db:
        deals = crud.list_bulk_deals(db, deal_date=None, limit=limit)

    enriched = enrich_bulk_deals(deals)
    clients = build_client_analytics(enriched)
    return {
        "date": None,
        "client_count": len(clients),
        "deal_count": len(enriched),
        "clients": clients,
    }


@bulk_deals_router.get("/dates")
def get_deal_dates():
    """Get list of available deal dates."""
    with SessionLocal() as db:
        dates = crud.get_bulk_deal_dates(db)
    return dates


@bulk_deals_router.post("/fetch")
def trigger_bulk_deals_fetch():
    """Manually trigger a bulk deals fetch from NSE."""
    result = fetch_and_store_bulk_deals()

    with SessionLocal() as db:
        crud.log_scan_run(
            db,
            scan_type="bulk_deals",
            status=result["status"] if result["status"] == "completed" else "failed",
            duration_sec=result.get("duration_sec"),
            matched_count=result.get("count"),
            triggered_by="manual",
        )

    return result
