"""Background scan scheduler service.

Checks schedule table every minute and triggers scans when the time matches.
Logs each execution to scan_history table.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from app.db import crud
from app.db.database import SessionLocal

logger = logging.getLogger(__name__)

_scheduler_thread: threading.Thread | None = None
_stop_event = threading.Event()

# Map scan_type to trigger functions
_SCAN_TRIGGERS: dict[str, Any] = {
    "nse_stocks": "day_scan",
    "brst": "screener",
    "multi_year": "screener",
    "golden": "screener",
    "weekly": "screener",
    "darvas": "screener",
    "mean_reversion": "screener",
    "vol_squeeze": "screener",
    "volume_surge": "screener",
    "bulk_deals": "bulk_deals",
    "sector_rotation": "sector_rotation",
    "ipo_intel": "ipo_intel",
}


def _parse_time(time_str: str) -> tuple[int, int]:
    """Parse HH:MM format to (hour, minute)."""
    try:
        parts = time_str.split(":")
        return int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        logger.warning(f"Invalid time format: {time_str}, using 09:00")
        return 9, 0


def _should_run_schedule(
    schedule: dict[str, Any],
    now_utc: datetime,
    last_run_times: dict[str, datetime],
) -> bool:
    """Check if a schedule should run now."""
    if not schedule["enabled"]:
        return False

    scan_type = schedule["scan_type"]
    target_hour, target_minute = _parse_time(schedule["time_of_day"])

    # Convert UTC time to the schedule's timezone for comparison
    tz_name = schedule.get("timezone", "Asia/Kolkata")
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("Asia/Kolkata")
    now_local = now_utc.astimezone(tz)
    
    # Check if current local time matches the schedule time (within the same minute)
    if now_local.hour != target_hour or now_local.minute != target_minute:
        return False

    # Check frequency
    frequency = schedule["frequency"]
    if frequency == "daily":
        last_run = last_run_times.get(scan_type)
        if last_run and last_run.astimezone(tz).date() == now_local.date():
            return False
        return True
    elif frequency == "weekly":
        if now_local.weekday() != 0:  # 0 = Monday
            return False
        last_run = last_run_times.get(scan_type)
        if last_run:
            days_since_last = (now_utc - last_run).days
            if days_since_last < 7:
                return False
        return True
    
    return False


def _trigger_day_scan() -> tuple[bool, str | None]:
    """Trigger day-scan fetch."""
    try:
        from app.services.day_scan import start_day_scan_fetch
        
        result = start_day_scan_fetch(force=False)
        if result.get("running"):
            return True, None
        else:
            return False, result.get("error")
    except Exception as e:
        logger.exception("Error triggering day scan")
        return False, str(e)


def _trigger_screener_scan(scan_type: str) -> tuple[bool, str | None]:
    """Trigger a screener scan via job_manager."""
    try:
        from app.services.job_manager import start_scan
        
        # Use empty filters for scheduled scans (defaults)
        filters: dict[str, Any] = {}
        
        # Dummy callback (no WebSocket for scheduled scans)
        def noop_callback(msg: dict) -> None:
            pass
        
        success = start_scan(scan_type, filters, noop_callback)
        if success:
            return True, None
        else:
            return False, f"{scan_type} scan already running"
    except Exception as e:
        logger.exception(f"Error triggering {scan_type} scan")
        return False, str(e)


def _trigger_bulk_deals() -> tuple[bool, str | None]:
    """Trigger bulk deals fetch from NSE."""
    try:
        from app.services.bulk_deals import fetch_and_store_bulk_deals

        result = fetch_and_store_bulk_deals()
        if result["status"] == "completed":
            return True, None
        elif result["status"] == "no_data":
            return True, "No bulk deals data available"
        else:
            return False, result.get("error")
    except Exception as e:
        logger.exception("Error triggering bulk deals fetch")
        return False, str(e)


def _trigger_sector_rotation() -> tuple[bool, str | None]:
    """Trigger sector rotation analysis."""
    try:
        from app.services.sector_rotation import run_sector_rotation_job

        result = run_sector_rotation_job()
        if result.get("status") == "ready":
            return True, None
        else:
            return False, result.get("error", "Unknown error")
    except Exception as e:
        logger.exception("Error triggering sector rotation")
        return False, str(e)


def _trigger_ipo_intel() -> tuple[bool, str | None]:
    """Trigger the headless-browser IPO GMP + subscription scrape."""
    try:
        from app.services.ipo_intel import run_ipo_intel_scrape

        run_ipo_intel_scrape()
        return True, None
    except Exception as e:
        logger.exception("Error triggering IPO intel scrape")
        return False, str(e)


def _run_scheduled_scan(schedule: dict[str, Any]) -> None:
    """Execute a scheduled scan and log the result."""
    scan_type = schedule["scan_type"]
    trigger_type = _SCAN_TRIGGERS.get(scan_type, "screener")
    
    start_time = time.time()
    logger.info(f"Running scheduled scan: {scan_type} (type: {trigger_type})")
    
    try:
        if trigger_type == "day_scan":
            success, error = _trigger_day_scan()
        elif trigger_type == "bulk_deals":
            success, error = _trigger_bulk_deals()
        elif trigger_type == "sector_rotation":
            success, error = _trigger_sector_rotation()
        elif trigger_type == "ipo_intel":
            success, error = _trigger_ipo_intel()
        else:
            success, error = _trigger_screener_scan(scan_type)
        
        duration = time.time() - start_time
        
        with SessionLocal() as db:
            crud.log_scan_run(
                db,
                scan_type=scan_type,
                status="completed" if success else "failed",
                duration_sec=duration,
                matched_count=None,  # Will be updated when scan completes
                error_message=error,
                triggered_by="scheduled",
            )
        
        if success:
            logger.info(f"Scheduled scan {scan_type} started successfully")
        else:
            logger.warning(f"Scheduled scan {scan_type} failed: {error}")
    
    except Exception as e:
        duration = time.time() - start_time
        logger.exception(f"Error running scheduled scan {scan_type}")
        
        with SessionLocal() as db:
            crud.log_scan_run(
                db,
                scan_type=scan_type,
                status="failed",
                duration_sec=duration,
                error_message=str(e),
                triggered_by="scheduled",
            )


def _scheduler_loop() -> None:
    """Main scheduler loop that runs every minute."""
    logger.info("Scan scheduler thread started")
    
    last_run_times: dict[str, datetime] = {}
    
    while not _stop_event.is_set():
        try:
            now = datetime.now(timezone.utc)
            
            # Fetch all schedules from database
            with SessionLocal() as db:
                schedules = crud.get_scan_schedules(db)
            
            # Check each schedule
            for schedule in schedules:
                if _should_run_schedule(schedule, now, last_run_times):
                    scan_type = schedule["scan_type"]
                    logger.info(f"Triggering scheduled scan: {scan_type}")
                    
                    # Run in a separate thread to avoid blocking
                    thread = threading.Thread(
                        target=_run_scheduled_scan,
                        args=(schedule,),
                        name=f"scheduled-{scan_type}",
                        daemon=True,
                    )
                    thread.start()
                    
                    # Update last run time
                    last_run_times[scan_type] = now
        
        except Exception:
            logger.exception("Error in scheduler loop")
        
        # Sleep for 30 seconds (check twice per minute for reliability)
        _stop_event.wait(30)
    
    logger.info("Scan scheduler thread stopped")


def start_scheduler() -> None:
    """Start the background scheduler thread."""
    global _scheduler_thread
    
    if _scheduler_thread and _scheduler_thread.is_alive():
        logger.warning("Scheduler already running")
        return
    
    _stop_event.clear()
    _scheduler_thread = threading.Thread(
        target=_scheduler_loop,
        name="scan-scheduler",
        daemon=True,
    )
    _scheduler_thread.start()
    logger.info("Scan scheduler started")


def stop_scheduler() -> None:
    """Stop the scheduler thread."""
    global _scheduler_thread
    
    if not _scheduler_thread or not _scheduler_thread.is_alive():
        logger.warning("Scheduler not running")
        return
    
    _stop_event.set()
    _scheduler_thread.join(timeout=5)
    logger.info("Scan scheduler stopped")
