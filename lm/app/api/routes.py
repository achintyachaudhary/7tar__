from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from app.config import OLLAMA_MODEL, QDRANT_COLLECTION
from app.db import stockdata
from app.llm import ollama_client
from app.services import stock_service
from app.vector import qdrant_store

router = APIRouter(prefix="/api")


class AnalyzeRequest(BaseModel):
    symbol: str
    question: str | None = None
    use_web: bool = False


class AskRequest(BaseModel):
    question: str
    use_web: bool = True


class IngestRequest(BaseModel):
    ticker: str
    title: str
    text: str
    source: str | None = None
    date: str | None = None


@router.get("/health")
def health():
    from app.services import searxng_client
    return {
        "ollama": ollama_client.is_available(),
        "qdrant": qdrant_store.is_available(),
        "database": stockdata.data_source(),
        "model": OLLAMA_MODEL,
        "collection": QDRANT_COLLECTION,
        "searxng": searxng_client.status(),
    }


@router.get("/web/status")
def web_status():
    from app.services import searxng_client
    return searxng_client.status()


@router.get("/stocks/search")
def search(q: str):
    if not q.strip():
        return []
    return stockdata.search_stocks(q.strip())


@router.post("/analyze")
def analyze(req: AnalyzeRequest):
    if not req.symbol.strip():
        raise HTTPException(400, "symbol is required")
    try:
        return stock_service.analyze_stock(req.symbol, req.question, use_web=req.use_web)
    except Exception as exc:
        raise HTTPException(502, f"analysis failed: {exc}")


@router.post("/ask")
def ask(req: AskRequest):
    if not req.question.strip():
        raise HTTPException(400, "question is required")
    try:
        return stock_service.ask_freeform(req.question, use_web=req.use_web)
    except Exception as exc:
        raise HTTPException(502, f"ask failed: {exc}")


@router.post("/news/ingest")
def ingest(req: IngestRequest):
    point_id = qdrant_store.upsert_document(
        req.text,
        {
            "ticker": req.ticker.upper(),
            "title": req.title,
            "source": req.source or "manual",
            "date": req.date or "",
        },
    )
    return {"id": point_id, "status": "stored"}


@router.get("/pulse/news")
def pulse_news(limit: int = 30):
    from app.services import pulse_service
    try:
        return pulse_service.get_news(limit=limit)
    except Exception as exc:
        raise HTTPException(502, f"pulse news unavailable: {exc}")


@router.post("/pulse/refresh")
def pulse_refresh(background_tasks: BackgroundTasks):
    from app.services import pulse_service
    if pulse_service.is_running():
        return {"started": False, "reason": "a refresh is already running"}
    background_tasks.add_task(pulse_service.refresh, "manual")
    return {"started": True}


@router.get("/inspect/overview")
def inspect_overview():
    from app.services import inspect_service
    try:
        return inspect_service.overview()
    except Exception as exc:
        raise HTTPException(502, f"inspect failed: {exc}")


@router.get("/inspect/vectors")
def inspect_vectors(offset: int = 0, limit: int = 20):
    from app.services import inspect_service
    try:
        return inspect_service.vector_points(offset=offset, limit=limit)
    except Exception as exc:
        raise HTTPException(502, f"vector inspect failed: {exc}")


@router.get("/inspect/pg-table/{table}")
def inspect_pg_table(table: str, offset: int = 0, limit: int = 50):
    from app.services import inspect_service
    try:
        return inspect_service.pg_table_rows(table, offset=offset, limit=limit)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(502, f"table read failed: {exc}")


@router.get("/admin/check")
def admin_check():
    from app.services.diagnostics import run_checks
    return run_checks()


@router.post("/admin/ingest-samples")
def admin_ingest_samples():
    from app.services.news_ingest import SAMPLES, ingest_articles
    try:
        stored = ingest_articles(SAMPLES)
    except Exception as exc:
        raise HTTPException(502, f"ingestion failed: {exc}")
    return {"stored": len(stored), "tickers": stored}
