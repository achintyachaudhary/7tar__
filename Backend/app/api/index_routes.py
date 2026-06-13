"""API routes for sector rotation and index analysis."""

from __future__ import annotations

import threading
from typing import Any

from fastapi import APIRouter, Query

from app.services.sector_rotation import (
    compute_sector_rotation,
    get_latest_rotation_from_db,
    save_rotation_to_db,
    SECTOR_INDICES,
    EXTRA_INDICES,
    BENCHMARK_TICKER,
    _fetch_yf_data,
)

index_router = APIRouter(prefix="/api/indices-analysis", tags=["indices"])

_rotation_computing = False


@index_router.get("/categories")
def get_categories():
    """Get available index categories and names."""
    return {
        "Sectoral": list(SECTOR_INDICES.keys()),
        "Broad Market": list(EXTRA_INDICES.keys()),
    }


@index_router.get("/rotation")
def get_sector_rotation():
    """Get latest sector rotation analysis from DB."""
    global _rotation_computing

    cached = get_latest_rotation_from_db()
    if cached:
        if _rotation_computing:
            cached["_refreshing"] = True
        return cached

    if _rotation_computing:
        return {"status": "computing", "message": "Sector rotation analysis in progress..."}

    return {"status": "empty", "message": "No analysis available. Click Refresh to compute."}


@index_router.post("/rotation/refresh")
def refresh_sector_rotation():
    """Trigger a fresh sector rotation computation (background thread)."""
    global _rotation_computing

    if _rotation_computing:
        return {"status": "already_running"}

    def _run():
        global _rotation_computing
        _rotation_computing = True
        try:
            result = compute_sector_rotation()
            if result.get("status") == "ready":
                save_rotation_to_db(result)
        except Exception:
            pass
        finally:
            _rotation_computing = False

    thread = threading.Thread(target=_run, name="sector-rotation", daemon=True)
    thread.start()
    return {"status": "started"}


@index_router.get("/chart/{index_name}")
def get_index_chart(
    index_name: str,
    period: str = Query("1y", pattern="^(1mo|3mo|6mo|1y|2y|5y)$"),
):
    """Fetch OHLC chart data for a specific index."""
    all_indices = {**SECTOR_INDICES, **EXTRA_INDICES}
    ticker = all_indices.get(index_name)
    if not ticker:
        return {"error": f"Unknown index: {index_name}", "available": list(all_indices.keys())}

    import yfinance as yf
    from app.utils.network import without_proxy

    try:
        with without_proxy():
            t = yf.Ticker(ticker)
            df = t.history(period=period, auto_adjust=True)

        if df is None or df.empty:
            return {"index_name": index_name, "period": period, "bars": []}

        bars = []
        for date, row in df.iterrows():
            bars.append({
                "time": date.strftime("%Y-%m-%d"),
                "open": round(float(row["Open"]), 2),
                "high": round(float(row["High"]), 2),
                "low": round(float(row["Low"]), 2),
                "close": round(float(row["Close"]), 2),
            })

        return {"index_name": index_name, "ticker": ticker, "period": period, "bars": bars}
    except Exception as e:
        return {"index_name": index_name, "period": period, "bars": [], "error": str(e)}
