"""Single multiplexed WebSocket endpoint for the entire application.

Replaces the per-scan-type WebSocket endpoints with one `/ws/app` connection.
Clients send JSON messages with a `channel` field; the hub dispatches to the
appropriate handler. Server pushes events back on the same socket.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.job_manager import cancel_scan, start_scan, start_day_scan, DAY_SCAN_TYPE

logger = logging.getLogger(__name__)

ws_hub_router = APIRouter()

# All currently connected clients
_clients: set[WebSocket] = set()
_clients_lock = asyncio.Lock()
_main_loop: asyncio.AbstractEventLoop | None = None


def set_ws_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Register the FastAPI event loop for thread-safe WS broadcasting."""
    global _main_loop
    _main_loop = loop


def broadcast_sync(message: dict[str, Any]) -> None:
    """Broadcast from a background thread (e.g. price-alert checker)."""
    loop = _main_loop
    if loop is None or loop.is_closed() or not loop.is_running():
        return
    try:
        asyncio.run_coroutine_threadsafe(broadcast(message), loop)
    except RuntimeError:
        pass


async def broadcast(message: dict[str, Any]) -> None:
    """Send a message to every connected WebSocket client."""
    async with _clients_lock:
        dead: list[WebSocket] = []
        for ws in _clients:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            _clients.discard(ws)


async def _send_safe(ws: WebSocket, message: dict[str, Any]) -> bool:
    """Send to one client; return False if the socket is dead."""
    try:
        await ws.send_json(message)
        return True
    except Exception:
        return False


def _make_ws_callback(ws: WebSocket, loop: asyncio.AbstractEventLoop):
    """Create a thread-safe callback that pushes messages to the WS client's event loop."""
    def callback(msg: dict[str, Any]) -> None:
        if loop.is_closed():
            return
        try:
            asyncio.run_coroutine_threadsafe(_send_safe(ws, msg), loop)
        except RuntimeError:
            pass
    return callback


def _make_broadcast_callback(loop: asyncio.AbstractEventLoop):
    """Create a thread-safe callback that broadcasts to all connected clients."""
    def callback(msg: dict[str, Any]) -> None:
        if loop.is_closed():
            return
        try:
            asyncio.run_coroutine_threadsafe(broadcast(msg), loop)
        except RuntimeError:
            pass
    return callback


async def _handle_scan_start(ws: WebSocket, msg: dict[str, Any], loop: asyncio.AbstractEventLoop) -> None:
    scan_type = msg.get("scan_type", "")
    filters = msg.get("filters") or {}

    # Broadcast scan progress to every connected client so all screener pages stay in sync.
    broadcast_cb = _make_broadcast_callback(loop)

    if scan_type == DAY_SCAN_TYPE:
        started = start_day_scan(filters, broadcast_cb)
    else:
        started = start_scan(scan_type, filters, broadcast_cb)

    if not started:
        logger.info("Scan %s attach/reject handled via broadcast", scan_type)


async def _handle_scan_status(ws: WebSocket, msg: dict[str, Any]) -> None:
    """Return live scan progress (one type or all scanners)."""
    from app.services.job_manager import get_all_scan_status, get_scan_status

    scan_type = msg.get("scan_type")
    if scan_type:
        payload = get_scan_status(str(scan_type))
    else:
        payload = get_all_scan_status()
    await _send_safe(ws, {
        "channel": "scan:status",
        "scan_type": scan_type,
        "status": payload,
    })


async def _handle_scan_cancel(ws: WebSocket, msg: dict[str, Any]) -> None:
    scan_type = msg.get("scan_type", "")
    cancelled = cancel_scan(scan_type)
    await _send_safe(ws, {
        "channel": "scan:cancelled",
        "scan_type": scan_type,
        "cancelled": cancelled,
    })


async def _handle_day_scan_status(ws: WebSocket, msg: dict[str, Any]) -> None:
    """Return current day-scan job status."""
    from app.services.day_scan import get_job_status, get_sync_status
    
    job = get_job_status()
    sync = get_sync_status()
    await _send_safe(ws, {
        "channel": "day-scan:status",
        "job": job,
        "sync": sync,
    })


async def _handle_live_watch(ws: WebSocket, msg: dict[str, Any]) -> None:
    """Register symbols a widget is displaying so live:ticks streams them.

    Registration is TTL'd — clients re-send while mounted; closed tabs decay.
    """
    from app.services.live_feed import register_watch_symbols

    symbols = msg.get("symbols")
    if isinstance(symbols, list):
        register_watch_symbols(symbols)


CHANNEL_HANDLERS = {
    "scan:start": _handle_scan_start,
    "scan:cancel": _handle_scan_cancel,
    "scan:status": _handle_scan_status,
    "day-scan:status": _handle_day_scan_status,
    "live:watch": _handle_live_watch,
}


@ws_hub_router.websocket("/ws/app")
async def websocket_app_hub(websocket: WebSocket) -> None:
    await websocket.accept()
    logger.info("App WS hub client connected")

    async with _clients_lock:
        _clients.add(websocket)

    loop = asyncio.get_running_loop()

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                import json
                msg = json.loads(raw)
            except (ValueError, TypeError):
                await _send_safe(websocket, {"channel": "error", "message": "Invalid JSON"})
                continue

            channel = msg.get("channel", "")
            handler = CHANNEL_HANDLERS.get(channel)

            if handler is None:
                await _send_safe(websocket, {
                    "channel": "error",
                    "message": f"Unknown channel: {channel}",
                })
                continue

            if channel == "scan:start":
                await handler(websocket, msg, loop)
            else:
                await handler(websocket, msg)

    except WebSocketDisconnect:
        logger.info("App WS hub client disconnected")
    except Exception:
        logger.exception("Error in WS hub")
    finally:
        async with _clients_lock:
            _clients.discard(websocket)
