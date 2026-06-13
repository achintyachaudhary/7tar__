"""Introspection for the UI Database section: which Postgres the lm service
uses, the databases on that server, lm-managed tables, and the Qdrant
vector-embedded documents (with a preview of the actual embedding vector).

All read-only.
"""

import logging

from sqlalchemy import text

from app.config import QDRANT_COLLECTION, QDRANT_URL
from app.db.stockdata import get_engine, data_source

log = logging.getLogger("lm.inspect")

# Tables the lm service creates and owns
LM_TABLES = ["lm_pulse_news", "lm_pulse_runs"]
# Screener tables lm reads (managed by the main app) — shown for context
SCREENER_TABLES = [
    "stock_prices_daily",
    "stock_universe",
    "stock_profiles",
    "day_scan_snapshots",
    "financial_cache",
    "holdings_cache",
]
# Everything browsable through /inspect/pg-table
_ALLOWED = set(LM_TABLES) | set(SCREENER_TABLES)

VECTOR_PREVIEW_DIMS = 8


def _mask_dsn(eng) -> str:
    try:
        return eng.url.render_as_string(hide_password=True)
    except Exception:
        return str(eng.url)


def _count(conn, table: str) -> int | None:
    try:
        return conn.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar()
    except Exception:
        return None  # table absent


def pg_overview() -> dict:
    eng = get_engine()
    if eng is None:
        return {"available": False, "reason": "no usable database connection"}

    url = eng.url
    dialect = eng.dialect.name
    out: dict = {
        "available": True,
        "source": data_source(),
        "dialect": dialect,
        "host": url.host,
        "port": url.port,
        "active_database": url.database,
        "user": url.username,
        "dsn_masked": _mask_dsn(eng),
        "server_databases": [],
        "lm_tables": [],
        "screener_tables": [],
    }

    with eng.connect() as conn:
        if dialect.startswith("postgres"):
            try:
                rows = conn.execute(text(
                    "SELECT datname, pg_size_pretty(pg_database_size(datname)) AS size "
                    "FROM pg_database WHERE datistemplate = false ORDER BY datname"
                ))
                out["server_databases"] = [
                    {
                        "name": r[0],
                        "size": r[1],
                        "active": r[0] == url.database,
                    }
                    for r in rows
                ]
            except Exception as exc:
                log.warning("could not list server databases: %s", exc)

        for t in LM_TABLES:
            c = _count(conn, t)
            if c is not None:
                out["lm_tables"].append(
                    {"name": t, "row_count": c, "managed_by": "Stock AI (lm)"}
                )
        for t in SCREENER_TABLES:
            c = _count(conn, t)
            if c is not None:
                out["screener_tables"].append(
                    {"name": t, "row_count": c, "managed_by": "Main app (read-only)"}
                )

    return out


def qdrant_overview() -> dict:
    from app.vector.qdrant_store import client

    out: dict = {"available": False, "url": QDRANT_URL, "collection": QDRANT_COLLECTION}
    try:
        qc = client()
        if not qc.collection_exists(QDRANT_COLLECTION):
            out["reason"] = "collection does not exist yet"
            return out
        info = qc.get_collection(QDRANT_COLLECTION)
        params = info.config.params.vectors
        out.update({
            "available": True,
            "points_count": qc.count(QDRANT_COLLECTION).count,
            "vector_size": getattr(params, "size", None),
            "distance": str(getattr(params, "distance", "")),
        })
    except Exception as exc:
        out["reason"] = str(exc)
    return out


def overview() -> dict:
    return {"postgres": pg_overview(), "qdrant": qdrant_overview()}


def vector_points(offset: int = 0, limit: int = 20) -> dict:
    """Browse embedded documents with a preview of each stored vector."""
    from app.vector.qdrant_store import client

    qc = client()
    if not qc.collection_exists(QDRANT_COLLECTION):
        return {"collection": QDRANT_COLLECTION, "total": 0, "points": [],
                "offset": offset, "limit": limit}

    total = qc.count(QDRANT_COLLECTION).count
    # small collections — fetch up to offset+limit (capped) then slice
    fetch = min(offset + limit, 500)
    records, _ = qc.scroll(
        QDRANT_COLLECTION,
        limit=fetch,
        with_payload=True,
        with_vectors=True,
    )
    page = records[offset:offset + limit]

    points = []
    for rec in page:
        payload = rec.payload or {}
        vec = rec.vector if isinstance(rec.vector, list) else None
        points.append({
            "id": str(rec.id),
            "ticker": payload.get("ticker"),
            "title": payload.get("title"),
            "source": payload.get("source"),
            "date": payload.get("date"),
            "text": payload.get("text"),
            "vector_dim": len(vec) if vec else None,
            "vector_preview": [round(v, 5) for v in vec[:VECTOR_PREVIEW_DIMS]] if vec else [],
        })

    info = qc.get_collection(QDRANT_COLLECTION)
    params = info.config.params.vectors
    return {
        "collection": QDRANT_COLLECTION,
        "vector_size": getattr(params, "size", None),
        "distance": str(getattr(params, "distance", "")),
        "total": total,
        "offset": offset,
        "limit": limit,
        "points": points,
    }


def pg_table_rows(table: str, offset: int = 0, limit: int = 50) -> dict:
    if table not in _ALLOWED:
        raise ValueError(f"table {table!r} is not browsable")
    eng = get_engine()
    if eng is None:
        raise RuntimeError("no usable database connection")

    with eng.connect() as conn:
        total = conn.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar()
        result = conn.execute(
            text(f'SELECT * FROM "{table}" LIMIT :lim OFFSET :off'),
            {"lim": limit, "off": offset},
        )
        columns = list(result.keys())
        rows = [dict(r._mapping) for r in result]

    # JSON-safe stringify of non-primitive cells
    for row in rows:
        for k, v in row.items():
            if v is not None and not isinstance(v, (str, int, float, bool)):
                row[k] = str(v)

    return {"table": table, "columns": columns, "rows": rows,
            "total": total, "offset": offset, "limit": limit}
