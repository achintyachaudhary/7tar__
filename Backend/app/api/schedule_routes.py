"""API routes for scan schedule configuration."""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db import crud
from app.db.database import SessionLocal

schedule_router = APIRouter(prefix="/api/schedules", tags=["schedules"])


class ScheduleUpdate(BaseModel):
    """Request body for updating a scan schedule."""

    enabled: bool
    frequency: str  # daily | weekly
    time_of_day: str  # HH:MM format
    timezone: str = "Asia/Kolkata"


@schedule_router.get("")
def get_schedules() -> list[dict[str, Any]]:
    """Get all scan schedules."""
    with SessionLocal() as db:
        return crud.get_scan_schedules(db)


@schedule_router.get("/{scan_type}")
def get_schedule(scan_type: str) -> dict[str, Any]:
    """Get a specific scan schedule."""
    with SessionLocal() as db:
        schedule = crud.get_scan_schedule(db, scan_type)
        if schedule is None:
            raise HTTPException(status_code=404, detail=f"Schedule not found: {scan_type}")
        return schedule


@schedule_router.put("/{scan_type}")
def update_schedule(scan_type: str, body: ScheduleUpdate) -> dict[str, Any]:
    """Update a scan schedule configuration."""
    # Validate frequency
    if body.frequency not in ("daily", "weekly"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid frequency: {body.frequency}. Must be 'daily' or 'weekly'.",
        )
    
    # Validate time_of_day format
    try:
        parts = body.time_of_day.split(":")
        hour, minute = int(parts[0]), int(parts[1])
        if not (0 <= hour < 24 and 0 <= minute < 60):
            raise ValueError
    except (ValueError, IndexError):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid time format: {body.time_of_day}. Must be HH:MM.",
        )
    
    with SessionLocal() as db:
        crud.upsert_scan_schedule(
            db,
            scan_type=scan_type,
            enabled=body.enabled,
            frequency=body.frequency,
            time_of_day=body.time_of_day,
            tz=body.timezone,
        )
        
        schedule = crud.get_scan_schedule(db, scan_type)
        if schedule is None:
            raise HTTPException(status_code=500, detail="Failed to save schedule")
        
        return schedule


@schedule_router.get("/history/recent")
def get_scan_history(limit: int = 50) -> list[dict[str, Any]]:
    """Get recent scan history."""
    if limit < 1 or limit > 200:
        raise HTTPException(status_code=400, detail="Limit must be between 1 and 200")
    
    with SessionLocal() as db:
        return crud.get_scan_history(db, limit=limit)


@schedule_router.get("/history/{history_id}")
def get_scan_history_detail(history_id: int) -> dict[str, Any]:
    """Get a single scan history entry with full symbol logs."""
    with SessionLocal() as db:
        entry = crud.get_scan_history_entry(db, history_id)
        if entry is None:
            raise HTTPException(status_code=404, detail=f"History entry not found: {history_id}")
        return entry
