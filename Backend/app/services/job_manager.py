"""Background scan job manager.

Spawns scans as daemon threads so they don't block the main async loop.
Each scan type can only have one active job at a time.
Progress/match/complete events are pushed via a callback to the WS hub.
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from functools import partial
from typing import Any, Callable

from tqdm import tqdm

from app.config import SCAN_MAX_WORKERS_DB, SCAN_PROGRESS_INTERVAL
from app.db import crud
from app.db.database import SessionLocal
from app.services.scan_context import (
    build_scan_context,
    clear_scan_context,
    init_scan_context,
)
from app.services.scan_helpers import slim_match_payload

logger = logging.getLogger(__name__)

# Maps scan_type -> scan function import path
SCAN_REGISTRY: dict[str, dict[str, Any]] = {
    "brst": {
        "module": "app.services.brst_screener",
        "fn": "scan_brst_symbol",
        "cache_key": "brst",
        "label": "BrSt",
    },
    "multi_year": {
        "module": "app.services.multi_year_screener",
        "fn": "scan_multi_year_symbol",
        "cache_key": "multi_year",
        "label": "Multi Year",
    },
    "golden": {
        "module": "app.services.golden_screener",
        "fn": "scan_golden_symbol",
        "cache_key": "golden",
        "label": "Golden",
    },
    "weekly": {
        "module": "app.services.weekly_screener",
        "fn": "scan_weekly_symbol",
        "cache_key": "weekly",
        "label": "Weekly",
    },
    "darvas": {
        "module": "app.services.darvas_screener",
        "fn": "scan_darvas_symbol",
        "cache_key": "darvas",
        "label": "Darvas Box",
    },
    "mean_reversion": {
        "module": "app.services.mean_reversion_screener",
        "fn": "scan_mean_reversion_symbol",
        "cache_key": "mean_reversion",
        "label": "Mean Reversion",
    },
    "vol_squeeze": {
        "module": "app.services.vol_squeeze_screener",
        "fn": "scan_vol_squeeze_symbol",
        "cache_key": "vol_squeeze",
        "label": "Volatility Squeeze",
    },
    "volume_surge": {
        "module": "app.services.volume_surge_screener",
        "fn": "scan_volume_surge_symbol",
        "cache_key": "volume_surge",
        "label": "Volume Surge",
    },
}

# Day scan uses its own job system but we can proxy progress into the WS hub.
DAY_SCAN_TYPE = "day_scan"

MessageCallback = Callable[[dict[str, Any]], None]

_active_jobs: dict[str, threading.Event] = {}
_scan_state: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()

_LOG_TAIL_MAX = 500


def is_scan_running(scan_type: str) -> bool:
    with _lock:
        event = _active_jobs.get(scan_type)
        return event is not None and not event.is_set()


def _snapshot_scan_status_unlocked(scan_type: str) -> dict[str, Any]:
    """Build status payload; caller must hold ``_lock``."""
    running = scan_type in _active_jobs and not _active_jobs[scan_type].is_set()
    state = dict(_scan_state.get(scan_type) or {})
    matches = list(state.get("matches") or [])
    logs = list(state.get("logs") or [])
    return {
        "scan_type": scan_type,
        "running": running,
        "scanned": int(state.get("scanned") or 0),
        "total": int(state.get("total") or 0),
        "symbol": str(state.get("symbol") or ""),
        "matches": matches,
        "match_count": len(matches),
        "logs": logs[-100:],
    }


def get_scan_status(scan_type: str) -> dict[str, Any]:
    """Live progress for a scan type (for UI reconnect / page navigation)."""
    with _lock:
        return _snapshot_scan_status_unlocked(scan_type)


def get_all_scan_status() -> dict[str, dict[str, Any]]:
    """Status for every registered scanner."""
    return {st: get_scan_status(st) for st in SCAN_REGISTRY}


def _update_scan_state(scan_type: str, **fields: Any) -> None:
    with _lock:
        state = _scan_state.setdefault(scan_type, {})
        state.update(fields)


def _append_scan_log(scan_type: str, entry: dict[str, Any]) -> None:
    with _lock:
        state = _scan_state.setdefault(scan_type, {})
        logs = list(state.get("logs") or [])
        logs.append(entry)
        state["logs"] = logs[-_LOG_TAIL_MAX:]


def _clear_scan_state(scan_type: str) -> None:
    with _lock:
        _scan_state.pop(scan_type, None)


def _emit_running_snapshot(scan_type: str, on_message: MessageCallback) -> None:
    with _lock:
        payload = _snapshot_scan_status_unlocked(scan_type)
    on_message({"channel": "scan:running", **payload})


def cancel_scan(scan_type: str) -> bool:
    with _lock:
        event = _active_jobs.get(scan_type)
        if event and not event.is_set():
            event.set()
            return True
    return False


def _load_scan_fn(scan_type: str, options: dict) -> Callable:
    import importlib
    reg = SCAN_REGISTRY[scan_type]
    mod = importlib.import_module(reg["module"])
    fn = getattr(mod, reg["fn"])
    return partial(fn, options=options)


def _get_symbols(filters: dict[str, Any]) -> list[str]:
    from app.services.stock_lists import filter_blacklisted

    with SessionLocal() as db:
        symbols = crud.list_stock_universe_with_filters(
            db,
            active_only=True,
            min_market_cap_cr=filters.get("min_market_cap_cr"),
            max_market_cap_cr=filters.get("max_market_cap_cr"),
        )
        blacklist = crud.get_blacklist_symbols(db)
        return filter_blacklisted(symbols, blacklist)


def _format_match_message(result: dict[str, Any]) -> str:
    parts = [f"price {result.get('price')}"]
    if result.get("distance_pct") is not None:
        parts.append(f"dist {result['distance_pct']}%")
    if result.get("tests_count") is not None:
        parts.append(f"tests {result['tests_count']}")
    if result.get("volume_confirmed"):
        parts.append("vol confirmed")
    elif result.get("volume_ratio") is not None:
        parts.append(f"vol {result['volume_ratio']}×")
    if result.get("rsi") is not None:
        parts.append(f"RSI {result['rsi']}")
    return " · ".join(parts)


def _emit_scan_log(
    scan_type: str,
    on_message: MessageCallback,
    *,
    symbol: str,
    outcome: str,
    message: str,
    scanned: int,
    total: int,
    match_count: int,
) -> None:
    ts = datetime.now(timezone.utc).isoformat()
    entry = {
        "ts": ts,
        "symbol": symbol,
        "outcome": outcome,
        "message": message,
        "scanned": scanned,
        "total": total,
        "match_count": match_count,
    }
    _append_scan_log(scan_type, entry)
    on_message({
        "channel": "scan:log",
        "scan_type": scan_type,
        **entry,
    })


def _persist_scan_history(
    *,
    scan_type: str,
    status: str,
    duration_sec: float,
    matched_count: int,
    total_scanned: int,
    triggered_by: str,
    error_message: str | None,
    details: dict[str, Any],
) -> int | None:
    try:
        with SessionLocal() as db:
            return crud.log_scan_run(
                db,
                scan_type=scan_type,
                status=status,
                duration_sec=duration_sec,
                matched_count=matched_count,
                total_scanned=total_scanned,
                error_message=error_message,
                triggered_by=triggered_by,
                details=details,
            )
    except Exception:
        logger.exception("Failed to persist scan history for %s", scan_type)
        return None


def start_scan(
    scan_type: str,
    filters: dict[str, Any],
    on_message: MessageCallback,
) -> bool:
    """Launch a background scan. Returns False if one is already running for this type."""
    if scan_type not in SCAN_REGISTRY:
        on_message({
            "channel": "scan:error",
            "scan_type": scan_type,
            "message": f"Unknown scan type: {scan_type}",
        })
        return False

    with _lock:
        existing = _active_jobs.get(scan_type)
        if existing and not existing.is_set():
            already_running = True
        else:
            already_running = False
            stop_event = threading.Event()
            _active_jobs[scan_type] = stop_event
            _scan_state[scan_type] = {
                "scanned": 0,
                "total": 0,
                "symbol": "",
                "matches": [],
                "logs": [],
            }

    if already_running:
        _emit_running_snapshot(scan_type, on_message)
        return False

    thread = threading.Thread(
        target=_run_scan,
        args=(scan_type, filters, on_message, stop_event),
        name=f"scan-{scan_type}",
        daemon=True,
    )
    thread.start()
    return True


def _run_scan(
    scan_type: str,
    filters: dict[str, Any],
    on_message: MessageCallback,
    stop_event: threading.Event,
) -> None:
    import time as _time

    reg = SCAN_REGISTRY[scan_type]
    label = reg["label"]
    logger.info("Starting %s scan in background thread", label)
    _start_time = _time.time()

    scan_logs: list[dict[str, Any]] = []
    matched_symbols: list[str] = []
    skipped_symbols: list[str] = []
    error_symbols: list[dict[str, str]] = []
    matches: list[dict[str, Any]] = []
    scanned = 0
    total_count = 0
    scan_config: dict[str, Any] = {}
    cancelled = False

    try:
        symbols = _get_symbols(filters)
        if not symbols:
            on_message({
                "channel": "scan:error",
                "scan_type": scan_type,
                "message": "No stocks match your filter criteria.",
            })
            return

        from app.services.scan_config import (
            build_scan_config,
            screener_options_from_config,
        )

        scan_config = filters.get("scan_config")
        if not isinstance(scan_config, dict):
            scan_config = build_scan_config(
                scan_type,
                scan_params={
                    k: filters[k]
                    for k in (
                        "min_market_cap_cr",
                        "max_market_cap_cr",
                        "require_volume_confirmation",
                    )
                    if filters.get(k) is not None
                },
                display_filters=filters.get("ui_filters") or {},
                universe={
                    "min_market_cap_cr": filters.get("min_market_cap_cr"),
                    "max_market_cap_cr": filters.get("max_market_cap_cr"),
                },
            )

        options = screener_options_from_config(scan_config)
        vol = filters.get("require_volume_confirmation")
        if vol is not None:
            options["require_volume_confirmation"] = bool(vol)

        scan_fn = _load_scan_fn(scan_type, options)
        total_count = len(symbols)
        preload_period = None
        try:
            from app.services.scan_context import preload_period_for_scan
            preload_period = preload_period_for_scan(scan_type, options)
        except Exception:
            pass

        _update_scan_state(scan_type, total=total_count, scanned=0, symbol="", matches=[], logs=[])
        on_message({
            "channel": "scan:init",
            "scan_type": scan_type,
            "total": total_count,
        })
        _emit_scan_log(
            scan_type,
            on_message,
            symbol="—",
            outcome="info",
            message=f"Queued {label} scan · {total_count} symbols",
            scanned=0,
            total=total_count,
            match_count=0,
        )

        workers = min(SCAN_MAX_WORKERS_DB, max(1, total_count))
        progress_every = max(1, SCAN_PROGRESS_INTERVAL)

        _emit_scan_log(
            scan_type,
            on_message,
            symbol="—",
            outcome="info",
            message=(
                f"Preloading price data from database ({preload_period or '5y'} window) — "
                "this usually takes 15–40s before symbols start scanning"
            ),
            scanned=0,
            total=total_count,
            match_count=0,
        )
        preload_start = _time.time()
        with SessionLocal() as db:
            ctx = build_scan_context(
                db,
                symbols,
                scan_type,
                preload_period=preload_period,
            )
        init_scan_context(ctx)
        preload_sec = _time.time() - preload_start
        _emit_scan_log(
            scan_type,
            on_message,
            symbol="—",
            outcome="info",
            message=f"Preload complete in {preload_sec:.1f}s — scanning {total_count} symbols ({workers} workers)",
            scanned=0,
            total=total_count,
            match_count=0,
        )

        def _scan_one(sym: str):
            try:
                return sym, scan_fn(sym), None
            except Exception as exc:
                return sym, None, str(exc)

        def _resolve_scan_result(raw: dict | None) -> tuple[dict | None, str | None]:
            """Split match payload vs reject sentinel (shared across all screeners)."""
            from app.services.scan_filters import is_reject_result, reject_reason

            if raw is None:
                return None, "scan error"
            if is_reject_result(raw):
                return None, reject_reason(raw)
            return raw, None

        pbar = tqdm(
            total=total_count,
            desc=f"{label} scan",
            unit="stk",
            dynamic_ncols=True,
            leave=True,
        )

        try:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(_scan_one, sym): sym for sym in symbols}

                for future in _iter_completed(futures):
                    if stop_event.is_set():
                        logger.info("%s scan cancelled by client", label)
                        cancelled = True
                        pool.shutdown(wait=False, cancel_futures=True)
                        break

                    try:
                        sym, raw, err = future.result()
                    except Exception as exc:
                        sym, raw, err = "Error", None, str(exc)

                    result, skip_reason = _resolve_scan_result(raw)

                    scanned += 1
                    pbar.update(1)
                    pbar.set_postfix(matches=len(matches), last=sym, refresh=False)

                    if err:
                        error_symbols.append({"symbol": sym, "error": err})
                        log_msg = f"error: {err}"
                        outcome = "error"
                        skipped_symbols.append(sym)
                    elif result:
                        slim = slim_match_payload(result)
                        matches.append(slim)
                        matched_symbols.append(sym)
                        log_msg = _format_match_message(result)
                        outcome = "match"
                        _update_scan_state(scan_type, matches=matches)
                        on_message({
                            "channel": "scan:match",
                            "scan_type": scan_type,
                            "data": slim,
                        })
                    else:
                        skipped_symbols.append(sym)
                        log_msg = skip_reason or "no match"
                        outcome = "skip"

                    _emit_scan_log(
                        scan_type,
                        on_message,
                        symbol=sym,
                        outcome=outcome,
                        message=log_msg,
                        scanned=scanned,
                        total=total_count,
                        match_count=len(matches),
                    )
                    with _lock:
                        scan_logs = list(_scan_state.get(scan_type, {}).get("logs") or [])

                    if scanned == total_count or scanned % progress_every == 0:
                        _update_scan_state(
                            scan_type,
                            scanned=scanned,
                            total=total_count,
                            symbol=sym,
                            matches=matches,
                        )
                        on_message({
                            "channel": "scan:progress",
                            "scan_type": scan_type,
                            "scanned": scanned,
                            "total": total_count,
                            "symbol": sym,
                            "match_count": len(matches),
                            "skipped_count": scanned - len(matches) - len(error_symbols),
                        })
        finally:
            pbar.close()
            clear_scan_context()

        duration = _time.time() - _start_time
        details = {
            "total": total_count,
            "scanned": scanned,
            "matched_count": len(matches),
            "skipped_count": len(skipped_symbols),
            "error_count": len(error_symbols),
            "matched_symbols": matched_symbols,
            "skipped_symbols": skipped_symbols,
            "errors": error_symbols,
            "scan_config": scan_config,
            "duration_sec": round(duration, 2),
            "log_tail": scan_logs[-_LOG_TAIL_MAX:],
        }

        if cancelled:
            history_id = _persist_scan_history(
                scan_type=scan_type,
                status="cancelled",
                duration_sec=duration,
                matched_count=len(matches),
                total_scanned=scanned,
                triggered_by="manual",
                error_message="Scan cancelled by user",
                details=details,
            )
            on_message({
                "channel": "scan:cancelled",
                "scan_type": scan_type,
                "scanned": scanned,
                "total": total_count,
                "match_count": len(matches),
                "history_id": history_id,
            })
            return

        # Persist to DB
        with SessionLocal() as db:
            crud.upsert_scan_result_cache(
                db,
                reg["cache_key"],
                matches,
                scanned=scanned,
                total=total_count,
                filter_data={
                    "scan_config": scan_config,
                    "min_market_cap_cr": filters.get("min_market_cap_cr"),
                    "max_market_cap_cr": filters.get("max_market_cap_cr"),
                    "ui_filters": scan_config.get("display_filters"),
                },
            )

        try:
            from app.services.live_trading import refresh_candidates_after_scan

            result = refresh_candidates_after_scan(scan_type)
            on_message({
                "channel": "candidates:updated",
                "scan_type": scan_type,
                "candidates_added": result.get("candidates_added", 0),
                "new_symbols": result.get("new_symbols", []),
            })
        except Exception:
            logger.exception("Live-trade candidate refresh failed after %s scan", scan_type)

        history_id = _persist_scan_history(
            scan_type=scan_type,
            status="completed",
            duration_sec=duration,
            matched_count=len(matches),
            total_scanned=scanned,
            triggered_by="manual",
            error_message=None,
            details=details,
        )

        on_message({
            "channel": "scan:complete",
            "scan_type": scan_type,
            "count": len(matches),
            "scanned": scanned,
            "total": total_count,
            "history_id": history_id,
        })

        on_message({
            "channel": "notification",
            "scan_type": scan_type,
            "count": len(matches),
        })

        _emit_scan_log(
            scan_type,
            on_message,
            symbol="—",
            outcome="info",
            message=f"Completed · {len(matches)} matches from {scanned} symbols in {duration:.1f}s",
            scanned=scanned,
            total=total_count,
            match_count=len(matches),
        )

        logger.info("%s scan completed: %d matches from %d symbols", label, len(matches), scanned)

    except Exception:
        logger.exception("%s scan failed", label)
        on_message({
            "channel": "scan:error",
            "scan_type": scan_type,
            "message": f"{label} scan failed unexpectedly.",
        })

        _persist_scan_history(
            scan_type=scan_type,
            status="failed",
            duration_sec=_time.time() - _start_time,
            matched_count=len(matches),
            total_scanned=scanned,
            triggered_by="manual",
            error_message=f"{label} scan failed unexpectedly.",
            details={
                "total": total_count,
                "scanned": scanned,
                "matched_count": len(matches),
                "matched_symbols": matched_symbols,
                "skipped_symbols": skipped_symbols,
                "errors": error_symbols,
                "scan_config": scan_config,
                "log_tail": scan_logs[-_LOG_TAIL_MAX:],
            },
        )
    finally:
        with _lock:
            _active_jobs.pop(scan_type, None)
        _clear_scan_state(scan_type)


def _iter_completed(futures: dict):
    """Yield futures as they complete (concurrent.futures.as_completed wrapper)."""
    from concurrent.futures import as_completed
    yield from as_completed(futures)


def _emit_day_scan_running_snapshot(on_message: MessageCallback) -> None:
    from app.services.day_scan import get_job_status

    status = get_job_status()
    on_message({
        "channel": "scan:running",
        "scan_type": DAY_SCAN_TYPE,
        "running": bool(status.get("running")),
        "scanned": int(status.get("processed") or 0),
        "total": int(status.get("total") or 0),
        "symbol": str(status.get("current_symbol") or ""),
        "matches": [],
        "match_count": 0,
    })


def start_day_scan(
    filters: dict[str, Any],
    on_message: MessageCallback,
) -> bool:
    """Start day scan as background thread, proxying progress to WS."""
    scan_type = DAY_SCAN_TYPE
    with _lock:
        existing = _active_jobs.get(scan_type)
        if existing and not existing.is_set():
            already_running = True
        else:
            already_running = False
            stop_event = threading.Event()
            _active_jobs[scan_type] = stop_event

    if already_running:
        _emit_day_scan_running_snapshot(on_message)
        return False

    thread = threading.Thread(
        target=_run_day_scan,
        args=(filters, on_message, stop_event),
        name="scan-day_scan",
        daemon=True,
    )
    thread.start()
    return True


def _run_day_scan(
    filters: dict[str, Any],
    on_message: MessageCallback,
    stop_event: threading.Event,
) -> None:
    """Run the existing day scan job and relay progress to WS."""
    try:
        from app.services.day_scan import start_day_scan_fetch, get_job_status
        import time

        force = filters.get("force", False)
        result = start_day_scan_fetch(force=force)

        if result.get("status") == "already_running":
            _emit_day_scan_running_snapshot(on_message)
            return

        # Poll the day scan job status and relay progress
        while not stop_event.is_set():
            status = get_job_status()
            on_message({
                "channel": "scan:progress",
                "scan_type": DAY_SCAN_TYPE,
                "scanned": status.get("processed", 0),
                "total": status.get("total", 0),
                "symbol": status.get("current_symbol", ""),
            })
            if not status.get("running", False):
                break
            time.sleep(2)

        on_message({
            "channel": "scan:complete",
            "scan_type": DAY_SCAN_TYPE,
            "count": get_job_status().get("fetched", 0),
        })
        on_message({
            "channel": "notification",
            "scan_type": DAY_SCAN_TYPE,
            "count": get_job_status().get("fetched", 0),
        })

    except Exception:
        logger.exception("Day scan via WS failed")
        on_message({
            "channel": "scan:error",
            "scan_type": DAY_SCAN_TYPE,
            "message": "Day scan failed unexpectedly.",
        })
    finally:
        with _lock:
            _active_jobs.pop(DAY_SCAN_TYPE, None)
