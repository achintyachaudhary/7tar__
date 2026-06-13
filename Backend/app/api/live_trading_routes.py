"""Live paper-trading engine API routes."""

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.services import live_trading

live_trading_router = APIRouter(prefix="/api/live-trading")


class ModeRequest(BaseModel):
    analysis_override: bool


class EntriesPauseRequest(BaseModel):
    entries_paused: bool


class PreviewStrategyRequest(BaseModel):
    strategy_key: str


class SyncExcludeItem(BaseModel):
    symbol: str
    source: str


class SyncRequest(BaseModel):
    """Optional; when empty, backend syncs all screeners with cached scan results."""
    scan_types: list[str] = []
    excluded: list[SyncExcludeItem] = []


@live_trading_router.get("/state")
def get_state() -> dict[str, Any]:
    return live_trading.get_state()


@live_trading_router.post("/mode")
def set_mode(req: ModeRequest) -> dict[str, Any]:
    return live_trading.set_analysis_override(req.analysis_override)


@live_trading_router.post("/entries-pause")
def set_entries_pause(req: EntriesPauseRequest) -> dict[str, Any]:
    """Kill switch: block new entries; open positions still managed."""
    return live_trading.set_entries_paused(req.entries_paused)


@live_trading_router.post("/preview-strategy")
def set_preview_strategy(req: PreviewStrategyRequest) -> dict[str, Any]:
    """Choose which strategy wallet drives the main dashboard."""
    return live_trading.set_preview_strategy(req.strategy_key)


@live_trading_router.post("/force-reset")
def force_reset() -> dict[str, Any]:
    """Clear all trades/candidates and reset all strategy wallets to ₹10L."""
    return live_trading.force_reset_portfolio()


@live_trading_router.post("/trades/{trade_id}/exit")
def exit_trade(trade_id: int) -> dict[str, Any]:
    """Manually close an open trade at the last known price."""
    return live_trading.manual_exit_trade(trade_id)


@live_trading_router.get("/candidates")
def candidates() -> dict[str, Any]:
    return {"candidates": live_trading.list_candidates()}


@live_trading_router.get("/trades")
def trades(
    status: str = Query("all", description="open | closed | all"),
    strategy: str | None = Query(None, description="Strategy key (default: preview)"),
) -> dict[str, Any]:
    return {"trades": live_trading.list_trades(status=status, strategy=strategy)}


@live_trading_router.get("/summary")
def summary() -> dict[str, Any]:
    return live_trading.strategy_summary()


@live_trading_router.get("/strategy-trades")
def get_strategy_trades(strategy: str = Query(..., description="Strategy key")) -> dict[str, Any]:
    return live_trading.strategy_trades(strategy)


@live_trading_router.post("/report")
def client_report() -> dict[str, Any]:
    """Email the current live-trading status snapshot to the client."""
    return live_trading.send_client_report()


@live_trading_router.get("/sync-preview")
def sync_preview() -> dict[str, Any]:
    """Stocks available from each screener cache (for sync picker)."""
    return live_trading.get_sync_preview()


@live_trading_router.post("/sync-screener")
def sync_screener(req: SyncRequest) -> dict[str, Any]:
    """Import candidates from screener caches; one consolidated email for new adds."""
    excluded = [{"symbol": e.symbol, "source": e.source} for e in req.excluded]
    return live_trading.sync_candidates_from_screeners(req.scan_types or None, excluded=excluded)


@live_trading_router.delete("/candidates")
def delete_candidate(
    symbol: str = Query(..., description="NSE symbol e.g. RELIANCE.NS"),
    source: str = Query(..., description="brst | multi_year | golden | weekly"),
) -> dict[str, Any]:
    """Remove a candidate from the watchlist (not while in_trade)."""
    return live_trading.remove_candidate(symbol, source)
