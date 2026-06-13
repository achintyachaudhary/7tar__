"""API routes for scraped IPO market intel (GMP + subscription)."""

from typing import Any

from fastapi import APIRouter

from app.db import crud
from app.db.database import SessionLocal

ipo_intel_router = APIRouter(prefix="/api/ipo-intel", tags=["ipo-intel"])


@ipo_intel_router.get("")
def list_intel() -> dict[str, Any]:
    from app.services.ipo_intel import get_ipo_intel_status

    with SessionLocal() as db:
        rows = crud.list_ipo_intel(db)
    return {
        "rows": rows,
        "count": len(rows),
        "job": get_ipo_intel_status(),
    }


@ipo_intel_router.post("/refresh")
def refresh_intel() -> dict[str, Any]:
    """Kick off a headless-browser scrape in the background."""
    from app.services.ipo_intel import start_ipo_intel_scrape

    return start_ipo_intel_scrape()


@ipo_intel_router.get("/status")
def intel_status() -> dict[str, Any]:
    from app.services.ipo_intel import get_ipo_intel_status

    return get_ipo_intel_status()
