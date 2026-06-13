"""Day scan and database browser API routes."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.db import crud
from app.db.database import engine, get_db
from app.models import OhlcBar
from app.services.day_scan import (
    get_day_scan_chart,
    get_job_status,
    get_listing_job_status,
    get_sync_status,
    list_day_scan_rows,
    start_day_scan_fetch,
    start_day_scan_fetch_if_needed,
    start_listing_fetch,
    start_volume_fetch,
)

day_scan_router = APIRouter(prefix="/api")


class DayScanRow(BaseModel):
    symbol: str
    company_name: str
    industry: str | None = None
    market_cap_cr: float | None = None
    pe_ratio: float | None = None
    roce_pct: float | None = None
    return_1d_pct: float | None = None
    return_1w_pct: float | None = None
    return_1m_pct: float | None = None
    return_1y_pct: float | None = None
    last_price: float | None = None
    prices_through_date: str | None = None
    updated_at: str | None = None


class DayScanListResponse(BaseModel):
    total: int
    rows: list[DayScanRow]


class DayScanChartResponse(BaseModel):
    symbol: str
    company_name: str
    bar_count: int
    from_date: str | None = None
    to_date: str | None = None
    bars: list[OhlcBar] = Field(default_factory=list)


class DayScanStatusResponse(BaseModel):
    running: bool
    total: int = 0
    processed: int = 0
    fetched: int = 0
    skipped: int = 0
    failed: int = 0
    current_symbol: str = ""
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None


class ListingFetchStatusResponse(DayScanStatusResponse):
    listing_total: int = 0
    listing_completed: int = 0
    all_listing_done: bool = False


class DayScanSyncStatusResponse(BaseModel):
    expected_through_date: str
    sync_through_date: str | None = None
    min_prices_through_date: str | None = None
    snapshot_count: int = 0
    universe_count: int = 0
    needs_sync: bool = False
    last_sync_at: str | None = None
    running: bool = False


class DbTableMeta(BaseModel):
    name: str
    row_count: int


class DbTablesResponse(BaseModel):
    tables: list[DbTableMeta]


class DbTableDataResponse(BaseModel):
    table: str
    columns: list[str]
    rows: list[dict[str, Any]]
    total: int
    offset: int
    limit: int


class WidgetPreferencesResponse(BaseModel):
    widget_id: str
    search_term: str = ""
    visible_columns: list[str] = Field(default_factory=list)
    column_filters: dict[str, Any] = Field(default_factory=dict)
    updated_at: str | None = None


class WidgetPreferencesUpdate(BaseModel):
    search_term: str | None = None
    visible_columns: list[str] | None = None
    column_filters: dict[str, Any] | None = None


# Tables safe to expose via browser (exclude nothing for local dev tool)
_DB_BROWSER_BLOCKLIST: set[str] = set()


@day_scan_router.get("/day-scan", response_model=DayScanListResponse)
def get_day_scan_table() -> DayScanListResponse:
    rows = list_day_scan_rows()
    return DayScanListResponse(
        total=len(rows),
        rows=[DayScanRow(**r) for r in rows],
    )


@day_scan_router.get("/day-scan/status", response_model=DayScanStatusResponse)
def day_scan_status() -> DayScanStatusResponse:
    return DayScanStatusResponse(**get_job_status())


@day_scan_router.get("/day-scan/sync-status", response_model=DayScanSyncStatusResponse)
def day_scan_sync_status() -> DayScanSyncStatusResponse:
    return DayScanSyncStatusResponse(**get_sync_status())


@day_scan_router.get("/day-scan/listing-status", response_model=ListingFetchStatusResponse)
def listing_fetch_status() -> ListingFetchStatusResponse:
    return ListingFetchStatusResponse(**get_listing_job_status())


@day_scan_router.post("/day-scan/fetch-from-listing")
def day_scan_fetch_from_listing() -> dict[str, Any]:
    return start_listing_fetch()


@day_scan_router.get("/day-scan/{symbol}/chart", response_model=DayScanChartResponse)
def day_scan_chart(
    symbol: str,
    interval: str = Query("1d", description="Candle interval: 1d | 1wk | 1mo"),
) -> DayScanChartResponse:
    raw = get_day_scan_chart(symbol, interval=interval)
    if not raw["bars"]:
        raise HTTPException(
            status_code=404,
            detail=f"No stored price history for {symbol}. Run Fetch All Stocks first.",
        )
    return DayScanChartResponse(
        symbol=raw["symbol"],
        company_name=raw["company_name"],
        bar_count=raw["bar_count"],
        from_date=raw["from_date"],
        to_date=raw["to_date"],
        bars=[OhlcBar(**b) for b in raw["bars"]],
    )


@day_scan_router.post("/day-scan/fetch")
def day_scan_fetch(force: bool = Query(False, description="Force refresh even if up to date")) -> dict[str, Any]:
    if force:
        return start_day_scan_fetch(force=True)
    return start_day_scan_fetch_if_needed(force=False)


@day_scan_router.post("/day-scan/fetch-volume")
def day_scan_fetch_volume(
    scope: str = Query("nifty50", description="nifty50 | all"),
) -> dict[str, Any]:
    """Download/refresh daily volume (and prices) for Nifty 50 or the whole NSE universe."""
    return start_volume_fetch(scope=scope)


# ── Database browser ──────────────────────────────────────────────────────────

@day_scan_router.get("/db/tables", response_model=DbTablesResponse)
def list_db_tables(db: Session = Depends(get_db)) -> DbTablesResponse:
    insp = inspect(engine)
    tables: list[DbTableMeta] = []
    for name in sorted(insp.get_table_names()):
        if name in _DB_BROWSER_BLOCKLIST:
            continue
        try:
            count = db.execute(text(f'SELECT COUNT(*) FROM "{name}"')).scalar() or 0
        except Exception:
            count = 0
        tables.append(DbTableMeta(name=name, row_count=int(count)))
    return DbTablesResponse(tables=tables)


@day_scan_router.get("/db/tables/{table_name}", response_model=DbTableDataResponse)
def get_db_table_data(
    table_name: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> DbTableDataResponse:
    insp = inspect(engine)
    valid_tables = set(insp.get_table_names()) - _DB_BROWSER_BLOCKLIST
    if table_name not in valid_tables:
        raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found")

    columns = [c["name"] for c in insp.get_columns(table_name)]
    total = db.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar() or 0

    result = db.execute(
        text(f'SELECT * FROM "{table_name}" LIMIT :limit OFFSET :offset'),
        {"limit": limit, "offset": offset},
    )
    rows = [dict(zip(columns, row)) for row in result.fetchall()]

    # Serialize datetime etc. to strings
    for row in rows:
        for k, v in row.items():
            if hasattr(v, "isoformat"):
                row[k] = v.isoformat()

    return DbTableDataResponse(
        table=table_name,
        columns=columns,
        rows=rows,
        total=int(total),
        offset=offset,
        limit=limit,
    )


# ── Widget preferences ────────────────────────────────────────────────────────

@day_scan_router.get("/widget-preferences/{widget_id}", response_model=WidgetPreferencesResponse)
def get_widget_prefs(widget_id: str, db: Session = Depends(get_db)) -> WidgetPreferencesResponse:
    """Get saved preferences for a specific widget."""
    prefs = crud.get_widget_preferences(db, widget_id)
    if prefs is None:
        # Return default empty preferences
        return WidgetPreferencesResponse(
            widget_id=widget_id,
            search_term="",
            visible_columns=[],
            column_filters={},
        )
    return WidgetPreferencesResponse(**prefs)


@day_scan_router.put("/widget-preferences/{widget_id}")
def update_widget_prefs(
    widget_id: str,
    update: WidgetPreferencesUpdate,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Update widget preferences."""
    crud.upsert_widget_preferences(
        db,
        widget_id=widget_id,
        search_term=update.search_term,
        visible_columns=update.visible_columns,
        column_filters=update.column_filters,
    )
    return {"status": "ok", "widget_id": widget_id}
