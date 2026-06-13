"""Price alert CRUD API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.db import crud
from app.db.database import SessionLocal
from app.services.price_alerts import _normalize_symbol, enrich_alerts_with_market_data

alert_router = APIRouter(prefix="/api/alerts")


@alert_router.get("/symbol-search")
def search_alert_symbols(
    q: str = Query("", min_length=1, max_length=80),
    limit: int = Query(12, ge=1, le=30),
) -> dict[str, Any]:
    with SessionLocal() as db:
        suggestions = crud.search_stock_suggestions(db, q, limit=limit)
    return {"suggestions": suggestions}


class CreateAlertRequest(BaseModel):
    symbol: str
    target_price: float = Field(gt=0)
    direction: str = "above"
    company_name: str | None = None
    email: str | None = None
    note: str | None = None


@alert_router.get("")
def list_alerts(
    active_only: bool = False,
    with_market: bool = Query(True, description="Attach LTP and % changes to active alerts"),
) -> dict[str, Any]:
    with SessionLocal() as db:
        alerts = crud.list_price_alerts(db, active_only=active_only)
    if with_market:
        alerts = enrich_alerts_with_market_data(alerts)
    return {"alerts": alerts}


@alert_router.post("")
def create_alert(req: CreateAlertRequest) -> dict[str, Any]:
    symbol = _normalize_symbol(req.symbol)
    if not symbol:
        raise HTTPException(status_code=400, detail="Symbol is required")
    if req.direction not in ("above", "below"):
        raise HTTPException(status_code=400, detail="direction must be 'above' or 'below'")

    with SessionLocal() as db:
        alert = crud.create_price_alert(
            db,
            symbol=symbol,
            target_price=req.target_price,
            direction=req.direction,
            company_name=req.company_name,
            email=req.email,
            note=req.note,
        )
    return {"alert": alert}


@alert_router.delete("/{alert_id}")
def delete_alert(alert_id: int) -> dict[str, Any]:
    with SessionLocal() as db:
        deleted = crud.delete_price_alert(db, alert_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"deleted": True}
