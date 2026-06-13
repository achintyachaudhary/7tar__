import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.config import PULSE_REFRESH_MINUTES

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("lm.main")


async def _pulse_schedule():
    """Fetch + AI-summarize Zerodha Pulse news every PULSE_REFRESH_MINUTES."""
    from app.services import pulse_service

    while True:
        try:
            await asyncio.to_thread(pulse_service.refresh, "schedule")
        except Exception as exc:
            log.warning("scheduled pulse refresh failed: %s", exc)
        await asyncio.sleep(PULSE_REFRESH_MINUTES * 60)


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(_pulse_schedule())
    yield
    task.cancel()


app = FastAPI(title="Stock AI (lm)", version="1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

UI_DIR = Path(__file__).resolve().parent.parent / "ui"
app.mount("/", StaticFiles(directory=UI_DIR, html=True), name="ui")
