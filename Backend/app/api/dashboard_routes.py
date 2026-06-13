"""Dashboard and preferences API routes."""

import threading
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db import crud

dashboard_router = APIRouter(prefix="/api")

# ── Pydantic schemas for request bodies ──────────────────────────────────────

class WidgetItem(BaseModel):
    widget_type: str
    size: str = "md"
    position: int = 0
    config: dict[str, Any] = {}


class LayoutPayload(BaseModel):
    widgets: list[WidgetItem]


class PreferencesPayload(BaseModel):
    preferences: dict[str, str]


class MarketIndexQuote(BaseModel):
    index_id: str
    display_name: str
    yf_symbol: str
    last_value: float | None = None
    change_abs: float | None = None
    change_pct: float | None = None
    updated_at: str | None = None


class MarketIndicesResponse(BaseModel):
    indices: list[MarketIndexQuote]
    market_open: bool = False
    session_phase: str = "closed"  # pre_open | open | closed
    as_of_label: str | None = None


class MarketIndexChartResponse(BaseModel):
    index_id: str
    display_name: str
    yf_symbol: str
    timeframe: str
    interval: str
    bars: list[dict[str, Any]] = Field(default_factory=list)


# ── In-memory cache for widget data (avoids re-scanning on every dashboard load) ─
_widget_cache: dict[str, Any] = {}
_widget_pending: set[str] = set()
_widget_lock = threading.Lock()
_WIDGET_CACHE_TTL_LIVE = 60  # market hours — keep dashboard data near-live
_WIDGET_CACHE_TTL_CLOSED = 300  # after close — values are end-of-day anyway


def _widget_ttl() -> int:
    from app.utils.market_hours import is_nse_data_live

    return _WIDGET_CACHE_TTL_LIVE if is_nse_data_live() else _WIDGET_CACHE_TTL_CLOSED


def _compute_widget_async(key: str, compute_fn) -> None:
    try:
        data = compute_fn()
        with _widget_lock:
            _widget_cache[key] = {"data": data, "expires_at": time.time() + _widget_ttl()}
    finally:
        with _widget_lock:
            _widget_pending.discard(key)


def _cached_widget(key: str, compute_fn):
    """Never blocks the dashboard: stale data (or a pending marker) is returned
    immediately while a background thread recomputes."""
    now = time.time()
    with _widget_lock:
        entry = _widget_cache.get(key)
        fresh = entry is not None and now < entry["expires_at"]
        should_compute = not fresh and key not in _widget_pending
        if should_compute:
            _widget_pending.add(key)

    if should_compute:
        threading.Thread(
            target=_compute_widget_async,
            args=(key, compute_fn),
            name=f"widget-{key}",
            daemon=True,
        ).start()

    if entry is not None:
        return entry["data"]  # possibly stale — refresh lands within seconds
    return {"pending": True}


# ── Layout endpoints ──────────────────────────────────────────────────────────

@dashboard_router.get("/dashboard/layout")
def get_layout(db: Session = Depends(get_db)) -> dict[str, Any]:
    widgets = crud.list_widgets(db)
    return {"widgets": widgets}


@dashboard_router.put("/dashboard/layout")
def save_layout(payload: LayoutPayload, db: Session = Depends(get_db)) -> dict[str, Any]:
    crud.save_widgets(db, [w.model_dump() for w in payload.widgets])
    return {"saved": len(payload.widgets)}


# ── Preferences endpoints ─────────────────────────────────────────────────────

@dashboard_router.get("/preferences")
def get_preferences(db: Session = Depends(get_db)) -> dict[str, Any]:
    return {"preferences": crud.get_all_prefs(db)}


@dashboard_router.put("/preferences")
def update_preferences(
    payload: PreferencesPayload, db: Session = Depends(get_db)
) -> dict[str, Any]:
    for key, value in payload.preferences.items():
        crud.set_pref(db, key, value)
    return {"saved": len(payload.preferences)}


# ── Widget data endpoints ─────────────────────────────────────────────────────

@dashboard_router.get("/market-indices", response_model=MarketIndicesResponse)
def market_indices(
    refresh: bool = Query(False, description="Force refresh from yfinance"),
) -> MarketIndicesResponse:
    from app.services.market_indices import ensure_market_indices_refreshed, list_market_indices
    from app.utils.market_hours import nse_session_phase

    if refresh:
        ensure_market_indices_refreshed(force=True)
    indices = list_market_indices(refresh_if_stale=not refresh)
    phase = nse_session_phase()
    labels = {"open": "Live", "pre_open": "Pre-open", "closed": "At close 3:30 pm IST"}
    return MarketIndicesResponse(
        indices=[MarketIndexQuote(**i) for i in indices],
        # market_open means "live prices exist" to the UI — pre-open included.
        market_open=phase != "closed",
        session_phase=phase,
        as_of_label=labels[phase],
    )


@dashboard_router.get("/market-indices/{index_id}/chart", response_model=MarketIndexChartResponse)
def market_index_chart(index_id: str) -> MarketIndexChartResponse:
    from app.services.market_indices import get_market_index_chart

    try:
        raw = get_market_index_chart(index_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return MarketIndexChartResponse(**raw)


@dashboard_router.post("/market-indices/refresh")
def market_indices_refresh() -> dict[str, str]:
    from app.services.market_indices import ensure_market_indices_refreshed

    ensure_market_indices_refreshed(force=True)
    return {"status": "ok"}


@dashboard_router.get("/vendors")
def list_vendors() -> dict[str, Any]:
    """Feature → data-vendor map for the Data Sources settings panel."""
    from app.services.vendors import upstox
    from app.services.vendors.registry import list_feature_vendors

    return {
        "features": list_feature_vendors(),
        "upstox_configured": upstox.is_configured(),
    }


@dashboard_router.get("/widgets/index-summary")
def index_summary() -> dict[str, Any]:
    """Quick snapshot of Nifty index benchmark data (shared market-index cache)."""

    def _fetch():
        try:
            from app.services.market_indices import list_market_indices

            result = [
                {
                    "name": q["display_name"],
                    "value": q["last_value"],
                    "change_pct": q["change_pct"],
                }
                for q in list_market_indices(refresh_if_stale=True)
                if q["last_value"] is not None
            ]
            return {"indices": result}
        except Exception:
            return {"indices": []}

    return _cached_widget("index_summary", _fetch)


def _today_quotes(symbols: list[str]) -> dict[str, dict[str, Any]]:
    """symbol → {ltp, prev_close, change_pct} from one Upstox batch LTP call.

    Change is vs the previous session close, so values are correct after
    hours (last close vs prior close) and live during the session.
    """
    from app.db.database import SessionLocal
    from app.services.vendors import upstox

    key_map: dict[str, str] = {}
    for sym in symbols:
        inst = upstox.resolve_instrument(sym)
        if inst:
            key_map[inst["instrument_key"]] = sym
    prices = upstox.fetch_ltp(list(key_map.keys()))

    out: dict[str, dict[str, Any]] = {}
    with SessionLocal() as db:
        for key, ltp in prices.items():
            sym = key_map.get(key)
            if sym is None or ltp <= 0:
                continue
            prev = crud._cached_prev_close(sym, db)
            change = (
                round((ltp - prev) / prev * 100, 2) if prev and prev > 0 else None
            )
            out[sym] = {"ltp": round(ltp, 2), "prev_close": prev, "change_pct": change}
    return out


@dashboard_router.get("/quotes/today")
def quotes_today(symbols: str = Query(..., description="Comma-separated symbols")) -> dict[str, Any]:
    """Today's LTP + % change for arbitrary symbols (Upstox batch LTP)."""
    from app.services.vendors.registry import use_upstox

    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()][:100]
    if not syms or not use_upstox("live_quotes"):
        return {"quotes": {}, "basis": "unavailable"}
    try:
        return {"quotes": _today_quotes(syms), "basis": "today"}
    except Exception:
        return {"quotes": {}, "basis": "unavailable"}


_PULSE_INDICES = [
    ("NSE_INDEX|Nifty 50", "NIFTY 50", "nifty"),
    ("NSE_INDEX|Nifty Bank", "NIFTY Bank", "banknifty"),
    ("NSE_INDEX|Nifty IT", "NIFTY IT", None),
    ("NSE_INDEX|Nifty Pharma", "NIFTY Pharma", None),
    ("NSE_INDEX|Nifty Auto", "NIFTY Auto", None),
    ("NSE_INDEX|Nifty FMCG", "NIFTY FMCG", None),
    ("NSE_INDEX|Nifty Metal", "NIFTY Metal", None),
    ("NSE_INDEX|Nifty Midcap 50", "NIFTY Midcap 50", None),
    ("NSE_INDEX|NIFTY SMLCAP 100", "NIFTY Smallcap 100", None),
]


@dashboard_router.get("/widgets/market-pulse")
def market_pulse() -> dict[str, Any]:
    """Tickertape-style index & sector tiles: LTP, today's %, 30d sparkline."""
    import json as _json

    import requests as _requests

    from app.db.database import SessionLocal
    from app.services.vendors import upstox
    from app.services.vendors.registry import use_upstox
    from app.utils.network import without_proxy

    def _fetch():
        if not use_upstox("market_indices"):
            return {"tiles": []}
        try:
            keys = [k for k, _, _ in _PULSE_INDICES]
            with without_proxy():
                resp = _requests.get(
                    "https://api.upstox.com/v2/market-quote/quotes",
                    params={"instrument_key": ",".join(keys)},
                    headers=upstox._headers(),
                    timeout=20,
                )
            resp.raise_for_status()
            data = (resp.json() or {}).get("data") or {}
            by_token = {
                str(v.get("instrument_token")): v for v in data.values()
            }

            sparks: dict[str, list[float]] = {}
            with SessionLocal() as db:
                for _, _, cache_id in _PULSE_INDICES:
                    if not cache_id:
                        continue
                    row = crud.get_market_index(db, cache_id)
                    if row and row.bars_json:
                        try:
                            bars = _json.loads(row.bars_json)[-30:]
                            sparks[cache_id] = [float(b["close"]) for b in bars]
                        except (ValueError, KeyError, TypeError):
                            pass

            tiles = []
            for key, label, cache_id in _PULSE_INDICES:
                q = by_token.get(key)
                if not q:
                    continue
                ltp = q.get("last_price")
                net = q.get("net_change")
                pct = None
                if ltp is not None and net is not None and (ltp - net) != 0:
                    pct = round(net / (ltp - net) * 100, 2)
                tiles.append(
                    {
                        "label": label,
                        "value": round(float(ltp), 2) if ltp is not None else None,
                        "change_pct": pct,
                        "spark": sparks.get(cache_id or "", []),
                    }
                )
            return {"tiles": tiles}
        except Exception:
            return {"tiles": []}

    return _cached_widget("market_pulse", _fetch)


@dashboard_router.get("/widgets/top-movers")
def top_movers() -> dict[str, Any]:
    """Top 5 gainers and losers — today's % via Upstox LTP, 5d scan fallback."""
    from app.services.screener import run_scan
    from app.services.vendors.registry import use_upstox
    from app.watchlists.indices import IndexId

    def _fetch_live():
        from app.config import NIFTY_50_TICKERS

        quotes = _today_quotes(NIFTY_50_TICKERS)
        rows = [
            {"symbol": sym, "price": q["ltp"], "change_5d_pct": q["change_pct"]}
            for sym, q in quotes.items()
            if q["change_pct"] is not None
        ]
        if len(rows) < 10:
            raise ValueError("too few live quotes — falling back to scan data")
        rows.sort(key=lambda r: r["change_5d_pct"], reverse=True)
        return {
            "gainers": rows[:5],
            "losers": sorted(rows, key=lambda r: r["change_5d_pct"])[:5],
            "basis": "today",
        }

    def _fetch():
        if use_upstox("live_quotes"):
            try:
                return _fetch_live()
            except Exception:
                pass
        try:
            scan = run_scan(min_score=0, limit=50, index=IndexId.NIFTY_50)
            all_stocks = scan.results
            with_change = [s for s in all_stocks if s.change_5d_pct is not None]
            gainers = sorted(with_change, key=lambda s: s.change_5d_pct or 0, reverse=True)[:5]
            losers = sorted(with_change, key=lambda s: s.change_5d_pct or 0)[:5]
            return {
                "gainers": [
                    {
                        "symbol": s.symbol,
                        "price": s.price,
                        "change_5d_pct": s.change_5d_pct,
                    }
                    for s in gainers
                ],
                "losers": [
                    {
                        "symbol": s.symbol,
                        "price": s.price,
                        "change_5d_pct": s.change_5d_pct,
                    }
                    for s in losers
                ],
            }
        except Exception:
            return {"gainers": [], "losers": []}

    return _cached_widget("top_movers", _fetch)
