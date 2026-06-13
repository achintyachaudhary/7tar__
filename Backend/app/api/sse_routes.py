"""SSE (Server-Sent Events) endpoint for real-time live trade updates.

The live trading engine pushes events here; connected browsers receive them
without polling. Active during market hours; sends heartbeat pings otherwise.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)

sse_router = APIRouter()

# All connected SSE subscriber queues
_sse_queues: list[asyncio.Queue] = []
_sse_lock = asyncio.Lock()
_main_loop: asyncio.AbstractEventLoop | None = None


def set_sse_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Register the FastAPI event loop for thread-safe SSE publishing."""
    global _main_loop
    _main_loop = loop


async def _add_subscriber() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=50)
    async with _sse_lock:
        _sse_queues.append(q)
    return q


async def _remove_subscriber(q: asyncio.Queue) -> None:
    async with _sse_lock:
        try:
            _sse_queues.remove(q)
        except ValueError:
            pass


def publish_sse_event(event_type: str, data: dict[str, Any]) -> None:
    """Thread-safe: push an SSE event to all connected subscribers.
    
    Called from the live-trading engine (which runs in a separate process/thread).
    Uses asyncio loop detection to handle cross-thread publishing.
    """
    payload = {"event": event_type, "data": data}
    loop = _main_loop
    if loop is not None and loop.is_running():
        loop.call_soon_threadsafe(_enqueue_sync, payload)
        return
    try:
        running = asyncio.get_running_loop()
        running.call_soon_threadsafe(_enqueue_sync, payload)
    except RuntimeError:
        logger.debug("SSE publish skipped — no running event loop")


def _enqueue_sync(payload: dict) -> None:
    for q in list(_sse_queues):
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            pass


def _format_sse(event: str, data: Any) -> str:
    encoded = json.dumps(data, default=str)
    return f"event: {event}\ndata: {encoded}\n\n"


async def _sse_generator(request: Request, queue: asyncio.Queue):
    """Async generator that yields SSE formatted events."""
    try:
        while True:
            if await request.is_disconnected():
                break
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=15.0)
                yield _format_sse(msg["event"], msg["data"])
            except asyncio.TimeoutError:
                yield _format_sse("heartbeat", {"status": "alive"})
    except asyncio.CancelledError:
        pass
    finally:
        await _remove_subscriber(queue)


@sse_router.get("/sse/live-trades")
async def sse_live_trades(request: Request):
    queue = await _add_subscriber()
    return StreamingResponse(
        _sse_generator(request, queue),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
