"""FastAPI application entry point."""

import os
from pathlib import Path

from dotenv import load_dotenv

_BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(_BACKEND_DIR / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.api.dashboard_routes import dashboard_router
from app.api.day_scan_routes import day_scan_router
from app.api.ipo_intel_routes import ipo_intel_router
from app.api.ipo_research_routes import ipo_research_router
from app.api.news_routes import news_router
from app.api.live_trading_routes import live_trading_router
from app.api.schedule_routes import schedule_router
from app.api.bulk_deals_routes import bulk_deals_router
from app.api.index_routes import index_router
from app.api.ws_hub import ws_hub_router
from app.api.sse_routes import sse_router
from app.api.alert_routes import alert_router
from app.api.scan_config_routes import scan_config_router
from app.api.stock_lists_routes import stock_lists_router
from app.db.database import Base, engine
from app.db.migrations import (
    migrate_ipo_listings,
    migrate_ipo_llm_research,
    migrate_ipo_ml_features,
    migrate_live_trading,
    migrate_stock_universe,
    migrate_stock_universe_columns,
    migrate_widget_preferences,
    migrate_scan_result_cache,
    migrate_scan_schedules,
    migrate_bulk_deals,
    migrate_sector_rotation,
    migrate_indexes,
    migrate_ipo_intel_columns,
    migrate_user_stock_lists,
)
import app.db.models as _db_models  # noqa: F401 — register ORM tables before create_all

# Ensure shared IPO table exists
_db_models.IpoListing.__table__.create(bind=engine, checkfirst=True)
from app.utils.network import configure_market_data_network
from app.utils.yfinance_quiet import configure_yfinance_logging

# Must run before any yfinance / NSE HTTP calls (Cursor sets a local proxy that blocks Yahoo).
configure_market_data_network()
configure_yfinance_logging()

CORS_ORIGINS = os.environ.get(
    "CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173",
).split(",")

app = FastAPI(
    title="Goldium",
    description="Screen NSE stocks using RSI, MACD, SMA, and more.",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in CORS_ORIGINS if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


_bridge_started = False


@app.on_event("startup")
def _init_db() -> None:
    Base.metadata.create_all(bind=engine)
    migrate_ipo_llm_research()
    migrate_ipo_ml_features()
    migrate_ipo_listings()
    migrate_stock_universe_columns()
    migrate_stock_universe()
    migrate_widget_preferences()
    migrate_scan_result_cache()
    migrate_live_trading()
    migrate_scan_schedules()
    migrate_bulk_deals()
    migrate_sector_rotation()
    migrate_indexes()
    migrate_ipo_intel_columns()
    migrate_user_stock_lists()

    from app.services.scan_scheduler import start_scheduler

    start_scheduler()

    from app.services.live_feed import start_live_feed

    start_live_feed()


@app.on_event("startup")
async def _start_live_trading_bridge() -> None:
    """Start engine + SSE/WS bridge after the asyncio loop is running."""
    global _bridge_started
    if _bridge_started:
        return

    import asyncio
    import threading

    from app.api.sse_routes import set_sse_loop
    from app.api.ws_hub import set_ws_loop
    from app.services.live_trading import start_engine
    from app.services.price_alerts import start_price_alert_checker

    loop = asyncio.get_running_loop()
    set_sse_loop(loop)
    set_ws_loop(loop)
    start_price_alert_checker()

    event_queue = start_engine()
    if event_queue is None:
        return

    def _bridge_events(eq, bridge_loop):
        while True:
            try:
                msg = eq.get(timeout=5)
            except Exception:
                continue

            event_type = msg.get("event", "")
            data = msg.get("data", {})

            try:
                from app.api.sse_routes import publish_sse_event

                publish_sse_event(event_type, data)
            except Exception:
                pass

            try:
                from app.api.ws_hub import broadcast

                ws_msg = {"channel": f"live-trading:{event_type}", **data}
                if bridge_loop.is_running():
                    asyncio.run_coroutine_threadsafe(broadcast(ws_msg), bridge_loop)
            except Exception:
                pass

    threading.Thread(
        target=_bridge_events,
        args=(event_queue, loop),
        name="live-trade-event-bridge",
        daemon=True,
    ).start()
    _bridge_started = True


app.include_router(router)
app.include_router(ws_hub_router)
app.include_router(dashboard_router)
app.include_router(day_scan_router)
app.include_router(ipo_intel_router)
app.include_router(ipo_research_router)
app.include_router(news_router)
app.include_router(live_trading_router)
app.include_router(schedule_router)
app.include_router(bulk_deals_router)
app.include_router(index_router)
app.include_router(sse_router)
app.include_router(alert_router)
app.include_router(scan_config_router)
app.include_router(stock_lists_router)
