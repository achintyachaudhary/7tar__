"""API route handlers."""

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect  # noqa: F401 (WS used by day-scan-sync)

from app.config import CACHE_TTL_SECONDS, DEFAULT_MIN_SCORE, DEFAULT_SCAN_LIMIT
from app.models import (
    ChartResponse,
    HealthResponse,
    IndicesResponse,
    IndexOption,
    IpoTrackResponse,
    OhlcBar,
    ScanResponse,
    StockDetail,
    StockInsightsResponse,
)
from app.schemas.ipo_llm import (
    IpoBatchFetchRequest,
    IpoBatchFetchResponse,
    IpoLlmResearchResponse,
    IpoLlmStatusResponse,
)
from app.services.ipo_llm_research import (
    batch_fetch_ipo_research,
    fetch_and_store_ipo_research,
    get_cached_ipo_research,
    get_ipo_llm_status_map,
)
from app.services.chart_data import VALID_TIMEFRAMES, fetch_chart_bars
from app.services.ipo_tracker import track_recent_ipos
from app.services.screener import analyze_symbol_detail, run_scan
from app.services.stock_insights import get_stock_insights
from app.watchlists.indices import IndexId, get_index_options
from app.watchlists.loader import get_watchlist_count

router = APIRouter()

_scan_cache: dict[str, Any] = {"payload": None, "expires_at": 0.0}


def _get_cached_scan(min_score: int, limit: int, index: IndexId) -> ScanResponse:
    key = f"{index.value}:{min_score}:{limit}"
    now = time.time()
    cached = _scan_cache.get("key")
    if (
        cached == key
        and _scan_cache.get("payload") is not None
        and now < _scan_cache.get("expires_at", 0)
    ):
        return _scan_cache["payload"]

    result = run_scan(min_score=min_score, limit=limit, index=index)
    _scan_cache["key"] = key
    _scan_cache["payload"] = result
    _scan_cache["expires_at"] = now + CACHE_TTL_SECONDS
    return result


def _parse_index(index: str) -> IndexId:
    try:
        return IndexId(index.lower())
    except ValueError as exc:
        valid = ", ".join(i.value for i in IndexId)
        raise HTTPException(
            status_code=400,
            detail=f"Invalid index '{index}'. Use one of: {valid}",
        ) from exc


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()


APPROX_SYMBOL_COUNTS: dict[str, int] = {
    IndexId.NIFTY_50.value: 50,
    IndexId.NIFTY_100.value: 100,
    IndexId.NIFTY_200.value: 200,
    IndexId.NIFTY_500.value: 500,
    IndexId.NSE_ALL.value: 2100,
}


@router.get("/api/indices", response_model=IndicesResponse)
def list_indices() -> IndicesResponse:
    options = get_index_options()
    return IndicesResponse(
        indices=[
            IndexOption(
                id=opt["id"],
                label=opt["label"],
                description=_index_description(
                    opt["description"],
                    opt["id"],
                ),
                slow_scan=bool(opt.get("slow_scan")),
            )
            for opt in options
        ],
    )


def _index_description(base: str, index_id: str) -> str:
    idx = IndexId(index_id)
    count = get_watchlist_count(idx) or APPROX_SYMBOL_COUNTS.get(index_id, 0)
    return f"{base} (~{count} symbols)"


@router.get("/api/scan", response_model=ScanResponse)
def scan(
    index: str = Query(IndexId.NIFTY_50.value, description="Watchlist: nifty50, nifty100, ..."),
    min_score: int = Query(DEFAULT_MIN_SCORE, ge=0, le=12),
    limit: int = Query(DEFAULT_SCAN_LIMIT, ge=1, le=500),
    refresh: bool = Query(False, description="Bypass cache"),
) -> ScanResponse:
    index_id = _parse_index(index)
    if refresh:
        _scan_cache["expires_at"] = 0
    return _get_cached_scan(min_score=min_score, limit=limit, index=index_id)


@router.get("/api/ipo", response_model=IpoTrackResponse)
def ipo_tracker(
    months: int = Query(2, ge=1, le=6, description="Look back 1, 2, or 6 months"),
    refresh: bool = Query(False, description="Bypass cache"),
) -> IpoTrackResponse:
    return track_recent_ipos(months=months, refresh=refresh)


@router.get("/api/ipo/llm-research/status", response_model=IpoLlmStatusResponse)
def ipo_llm_research_status(
    symbols: str = Query(..., description="Comma-separated NSE symbols"),
) -> IpoLlmStatusResponse:
    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
    return get_ipo_llm_status_map(symbol_list)


@router.post("/api/ipo/llm-research/batch", response_model=IpoBatchFetchResponse)
def ipo_llm_research_batch(body: IpoBatchFetchRequest) -> IpoBatchFetchResponse:
    try:
        return batch_fetch_ipo_research(body.items, skip_fetched=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/ipo/{symbol}/llm-research", response_model=IpoLlmResearchResponse)
def get_ipo_llm_research(symbol: str) -> IpoLlmResearchResponse:
    result = get_cached_ipo_research(symbol)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No IPO LLM research cached for {symbol}. POST to generate.",
        )
    return result


@router.post("/api/ipo/{symbol}/llm-research", response_model=IpoLlmResearchResponse)
def generate_ipo_llm_research(
    symbol: str,
    company_name: str | None = Query(None, description="Optional company name for prompt"),
    refresh: bool = Query(False, description="Bypass cache and call LLM again"),
) -> IpoLlmResearchResponse:
    try:
        return fetch_and_store_ipo_research(
            symbol,
            company_name=company_name,
            force_refresh=refresh,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("IPO LLM research failed for %s", symbol)
        raise HTTPException(status_code=502, detail=f"LLM request failed: {exc}") from exc


@router.get("/api/stock/{symbol}/chart", response_model=ChartResponse)
def stock_chart(
    symbol: str,
    timeframe: str = Query("1M", description="1D, 1W, 1M, 3M, 6M, 1Y, 5Y"),
) -> ChartResponse:
    tf = timeframe.upper()
    if tf not in VALID_TIMEFRAMES:
        valid = ", ".join(sorted(VALID_TIMEFRAMES))
        raise HTTPException(status_code=400, detail=f"Invalid timeframe '{timeframe}'. Use: {valid}")
    raw = fetch_chart_bars(symbol, tf)
    return ChartResponse(
        symbol=raw["symbol"],
        timeframe=raw["timeframe"],
        interval=raw["interval"],
        tv_interval=raw["tv_interval"],
        bars=[OhlcBar(**b) for b in raw["bars"]],
    )


@router.get("/api/stock/{symbol}/insights", response_model=StockInsightsResponse)
def stock_insights(symbol: str) -> StockInsightsResponse:
    return get_stock_insights(symbol)


@router.post("/api/refresh/stock/{symbol}", response_model=StockInsightsResponse)
def refresh_stock(symbol: str) -> StockInsightsResponse:
    """Force-refresh all DB-cached data (profile, holdings, financials) for a symbol."""
    return get_stock_insights(symbol, force_refresh=True)


@router.get("/api/stock/{symbol}", response_model=StockDetail)
def stock_detail(symbol: str) -> StockDetail:
    detail = analyze_symbol_detail(symbol)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"No data for symbol: {symbol}")
    return detail



# Old per-scan WebSocket endpoints removed -- all scans now go through /ws/app hub.
# See Backend/app/api/ws_hub.py and Backend/app/services/job_manager.py.


@router.get("/api/rules")
def list_screening_rules() -> dict[str, Any]:
    """Scanner definitions: core criteria + configurable parameters."""
    from app.services.scan_definitions import list_scan_definitions

    defs = list_scan_definitions()
    return {"definitions": defs, "rules": defs}


@router.get("/api/rules/{rule_id}")
def get_screening_rule(rule_id: str) -> dict[str, Any]:
    from app.services.scan_definitions import get_scan_definition

    defn = get_scan_definition(rule_id)
    if not defn:
        raise HTTPException(status_code=404, detail=f"No scanner: {rule_id}")
    return defn


@router.get("/api/scans/status")
def scans_status(scan_type: str | None = None) -> dict[str, Any]:
    """Live progress for background scans (used when a screener page opens mid-scan)."""
    from app.services.job_manager import get_all_scan_status, get_scan_status

    if scan_type:
        return get_scan_status(scan_type)
    return get_all_scan_status()


@router.get("/api/brst/scan-results")
def get_brst_scan_results() -> dict[str, Any]:
    from app.db.database import SessionLocal
    from app.db import crud

    with SessionLocal() as db:
        cached = crud.get_scan_result_cache(db, "brst")
    if cached is None:
        return {
            "scan_type": "brst",
            "matches": [],
            "filter": {},
            "scanned": 0,
            "total": 0,
            "last_scanned_at": None,
        }
    return cached


@router.get("/api/weekly-stocks/scan-results")
def get_weekly_scan_results() -> dict[str, Any]:
    from app.db.database import SessionLocal
    from app.db import crud
    from app.services.holdings import normalize_scan_cache_payload

    with SessionLocal() as db:
        cached = crud.get_scan_result_cache(db, "weekly")
    if cached is None:
        return {
            "scan_type": "weekly",
            "matches": [],
            "filter": {},
            "scanned": 0,
            "total": 0,
            "last_scanned_at": None,
        }
    return normalize_scan_cache_payload(cached)


@router.get("/api/darvas/scan-results")
def get_darvas_scan_results() -> dict[str, Any]:
    from app.db.database import SessionLocal
    from app.db import crud

    with SessionLocal() as db:
        cached = crud.get_scan_result_cache(db, "darvas")
    if cached is None:
        return {
            "scan_type": "darvas",
            "matches": [],
            "filter": {},
            "scanned": 0,
            "total": 0,
            "last_scanned_at": None,
        }
    return cached


@router.get("/api/golden-stocks/scan-results")
def get_golden_scan_results() -> dict[str, Any]:
    from app.db.database import SessionLocal
    from app.db import crud
    from app.services.holdings import normalize_scan_cache_payload

    with SessionLocal() as db:
        cached = crud.get_scan_result_cache(db, "golden")
    if cached is None:
        return {
            "scan_type": "golden",
            "matches": [],
            "filter": {},
            "scanned": 0,
            "total": 0,
            "last_scanned_at": None,
        }
    return normalize_scan_cache_payload(cached)


@router.get("/api/multi-year/scan-results")
def get_multi_year_scan_results() -> dict[str, Any]:
    from app.db.database import SessionLocal
    from app.db import crud

    with SessionLocal() as db:
        cached = crud.get_scan_result_cache(db, "multi_year")
    if cached is None:
        return {
            "scan_type": "multi_year",
            "matches": [],
            "filter": {},
            "scanned": 0,
            "total": 0,
            "last_scanned_at": None,
        }
    return cached


@router.get("/api/mean-reversion/scan-results")
def get_mean_reversion_scan_results() -> dict[str, Any]:
    from app.db.database import SessionLocal
    from app.db import crud

    with SessionLocal() as db:
        cached = crud.get_scan_result_cache(db, "mean_reversion")
    if cached is None:
        return {
            "scan_type": "mean_reversion",
            "matches": [],
            "filter": {},
            "scanned": 0,
            "total": 0,
            "last_scanned_at": None,
        }
    return cached


@router.get("/api/vol-squeeze/scan-results")
def get_vol_squeeze_scan_results() -> dict[str, Any]:
    from app.db.database import SessionLocal
    from app.db import crud

    with SessionLocal() as db:
        cached = crud.get_scan_result_cache(db, "vol_squeeze")
    if cached is None:
        return {
            "scan_type": "vol_squeeze",
            "matches": [],
            "filter": {},
            "scanned": 0,
            "total": 0,
            "last_scanned_at": None,
        }
    return cached


@router.get("/api/volume-surge/scan-results")
def get_volume_surge_scan_results() -> dict[str, Any]:
    from app.db.database import SessionLocal
    from app.db import crud

    with SessionLocal() as db:
        cached = crud.get_scan_result_cache(db, "volume_surge")
    if cached is None:
        return {
            "scan_type": "volume_surge",
            "matches": [],
            "filter": {},
            "scanned": 0,
            "total": 0,
            "last_scanned_at": None,
        }
    return cached


# Legacy route - use /ws/app with scan:start channel instead