"""API for user favorite and blacklisted stock lists."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.db import crud
from app.db.database import SessionLocal

stock_lists_router = APIRouter(prefix="/api/stock-lists", tags=["stock-lists"])


class StockListReplaceRequest(BaseModel):
    favorites: list[str] = Field(default_factory=list)
    blacklist: list[str] = Field(default_factory=list)
    notes: dict[str, str] | None = None


class StockListToggleRequest(BaseModel):
    note: str | None = None


@stock_lists_router.get("")
def get_stock_lists() -> dict[str, Any]:
    with SessionLocal() as db:
        return crud.get_user_stock_lists(db)


@stock_lists_router.get("/table")
def get_stock_lists_table() -> dict[str, Any]:
    """Favorites/fishy/blacklist merged with live day %, 7d %, market cap, industry."""
    from app.services.stock_lists import build_enriched_stock_list_rows

    rows = build_enriched_stock_list_rows()
    return {"rows": rows, "count": len(rows)}


@stock_lists_router.put("")
def replace_stock_lists(body: StockListReplaceRequest) -> dict[str, Any]:
    with SessionLocal() as db:
        return crud.replace_user_stock_lists(
            db,
            favorites=body.favorites,
            blacklist=body.blacklist,
            notes=body.notes,
        )


@stock_lists_router.post("/{list_type}/{symbol}")
def add_to_stock_list(
    list_type: str,
    symbol: str,
    body: StockListToggleRequest | None = None,
) -> dict[str, Any]:
    if list_type not in ("favorite", "fishy", "blacklist", "following"):
        raise HTTPException(
            status_code=400,
            detail="list_type must be favorite, fishy, blacklist, or following",
        )
    note = body.note if body else None
    try:
        with SessionLocal() as db:
            entry = crud.upsert_stock_list_entry(
                db, symbol=symbol, list_type=list_type, note=note
            )
            lists = crud.get_user_stock_lists(db)
            return {"entry": entry, **lists}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@stock_lists_router.delete("/{list_type}/{symbol}")
def remove_from_stock_list(list_type: str, symbol: str) -> dict[str, Any]:
    if list_type not in ("favorite", "fishy", "blacklist", "following"):
        raise HTTPException(
            status_code=400,
            detail="list_type must be favorite, fishy, blacklist, or following",
        )
    with SessionLocal() as db:
        removed = crud.remove_stock_list_entry(db, symbol=symbol, list_type=list_type)
        lists = crud.get_user_stock_lists(db)
        return {"removed": removed, **lists}
