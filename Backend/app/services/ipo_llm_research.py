"""Fetch IPO subscription details via LLM and persist to SQLite."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

from pydantic import ValidationError

from app.db import crud
from app.db.database import SessionLocal
from app.schemas.ipo_llm import (
    IpoBatchFetchItem,
    IpoBatchFetchResponse,
    IpoBatchFetchResultItem,
    IpoLlmResearchResponse,
    IpoLlmStatusItem,
    IpoLlmStatusResponse,
    IpoSubscriptionResearch,
)
from app.services.llm import get_llm_provider

logger = logging.getLogger(__name__)

SYSTEM_INSTRUCTION = """You are a financial data assistant for Indian stock IPOs.
Return ONLY valid JSON matching the exact schema requested.
Use publicly known IPO facts from NSE/BSE prospectus and subscription data.
REQUIRED: always set company_name, ticker_symbol, bidding_period dates, pricing, and issue_type when known.
For unknown numeric fields use null. For unknown text fields use empty string "", never null for strings.
Dates as YYYY-MM-DD. Amounts in INR as numbers without currency symbols."""

JSON_SCHEMA_HINT = """
{
  "company_name": "string",
  "ticker_symbol": "string (NSE symbol without .NS)",
  "bidding_period": { "open_date": "YYYY-MM-DD", "close_date": "YYYY-MM-DD" },
  "pricing": {
    "price_band_inr": { "floor": number, "cap": number },
    "final_issue_price_inr": number
  },
  "issue_details": {
    "total_issue_size_crores_inr": number,
    "total_shares_offered": integer,
    "total_shares_bid_for": integer,
    "issue_type": "string e.g. 100% Fresh Issue"
  },
  "subscription_summary": {
    "overall_times_subscribed": number,
    "category_breakdown": {
      "qualified_institutional_buyers_qib": { "shares_offered": integer, "times_subscribed": number },
      "non_institutional_investors_nii": { "shares_offered": integer, "times_subscribed": number },
      "retail_individual_investors_rii": { "shares_offered": integer, "times_subscribed": number },
      "employee_reservation": { "shares_offered": integer, "times_subscribed": number }
    }
  }
}
"""


def _normalize_symbol(symbol: str) -> str:
    return symbol.upper().replace(".NS", "").replace(".BO", "").strip()


def _build_prompt(ticker: str, company_name: str | None) -> str:
    name_part = f" ({company_name})" if company_name else ""
    return (
        f"For {ticker}{name_part} Indian stock IPO, provide subscription rates and IPO type "
        f"in this exact JSON format only. Include QIB, NII, retail (RII), and employee "
        f"categories where applicable. No markdown, no explanation, JSON object only:\n"
        f"{JSON_SCHEMA_HINT}"
    )


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def _apply_request_defaults(
    data: dict,
    symbol: str,
    company_name: str | None,
) -> dict:
    """Fill gaps when the model returns null for fields we already know from the request."""
    out = dict(data) if isinstance(data, dict) else {}

    if not out.get("ticker_symbol"):
        out["ticker_symbol"] = symbol
    if not out.get("company_name"):
        out["company_name"] = (company_name or "").strip() or symbol

    for key in ("bidding_period", "pricing", "issue_details", "subscription_summary"):
        if out.get(key) is None:
            out[key] = {}

    return out


def _overall_subscription(payload_json: str) -> float | None:
    try:
        raw = json.loads(payload_json)
        sub = raw.get("subscription_summary") or {}
        val = sub.get("overall_times_subscribed")
        return float(val) if val is not None else None
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def _row_to_status_item(symbol: str, row) -> IpoLlmStatusItem:
    if row is None:
        return IpoLlmStatusItem(symbol=symbol, status="pending")
    status = row.status or "fetched"
    if status == "failed":
        return IpoLlmStatusItem(
            symbol=symbol,
            status="failed",
            fetched_at=row.fetched_at.isoformat() if row.fetched_at else None,
            error_message=row.error_message,
        )
    return IpoLlmStatusItem(
        symbol=symbol,
        status="fetched",
        fetched_at=row.fetched_at.isoformat() if row.fetched_at else None,
        overall_times_subscribed=_overall_subscription(row.payload_json),
    )


def get_ipo_llm_status_map(symbols: list[str]) -> IpoLlmStatusResponse:
    normalized = [_normalize_symbol(s) for s in symbols if s]
    with SessionLocal() as db:
        rows = crud.list_ipo_llm_status(db, normalized)
    statuses = [_row_to_status_item(sym, rows.get(sym)) for sym in normalized]
    return IpoLlmStatusResponse(statuses=statuses)


def get_cached_ipo_research(symbol: str) -> IpoLlmResearchResponse | None:
    symbol = _normalize_symbol(symbol)
    with SessionLocal() as db:
        row = crud.get_ipo_llm_research(db, symbol)
        if not row or (row.status or "fetched") != "fetched":
            return None
        data = IpoSubscriptionResearch.model_validate(json.loads(row.payload_json))
        return IpoLlmResearchResponse(
            symbol=symbol,
            provider=row.provider,
            fetched_at=row.fetched_at.isoformat(),
            data=data,
            from_cache=True,
            status="fetched",
        )


def _record_fetch_failure(symbol: str, provider: str, message: str) -> None:
    with SessionLocal() as db:
        crud.upsert_ipo_llm_failed(db, symbol, provider, message)


def fetch_and_store_ipo_research(
    symbol: str,
    company_name: str | None = None,
    *,
    force_refresh: bool = False,
) -> IpoLlmResearchResponse:
    symbol = _normalize_symbol(symbol)

    if not force_refresh:
        cached = get_cached_ipo_research(symbol)
        if cached:
            return cached

    provider = get_llm_provider()
    try:
        prompt = _build_prompt(symbol, company_name)
        raw = provider.generate_json(prompt, system_instruction=SYSTEM_INSTRUCTION)
        parsed = _apply_request_defaults(_extract_json(raw), symbol, company_name)
        research = IpoSubscriptionResearch.model_validate(parsed)
    except (json.JSONDecodeError, ValidationError) as exc:
        logger.error("Invalid LLM JSON for %s: %s", symbol, exc)
        _record_fetch_failure(symbol, provider.provider_id, f"Invalid JSON: {exc}")
        raise ValueError(f"LLM returned invalid JSON: {exc}") from exc
    except Exception as exc:
        logger.error("IPO LLM fetch failed for %s: %s", symbol, exc)
        _record_fetch_failure(symbol, provider.provider_id, str(exc))
        raise

    if research.ticker_symbol.upper().replace(".NS", "") != symbol:
        research = research.model_copy(update={"ticker_symbol": symbol})

    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        crud.upsert_ipo_llm_research(
            db,
            symbol=symbol,
            provider=provider.provider_id,
            payload_json=research.model_dump_json(),
            fetched_at=now,
        )

    return IpoLlmResearchResponse(
        symbol=symbol,
        provider=provider.provider_id,
        fetched_at=now.isoformat(),
        data=research,
        from_cache=False,
        status="fetched",
    )


def batch_fetch_ipo_research(
    items: list[IpoBatchFetchItem],
    *,
    skip_fetched: bool = True,
) -> IpoBatchFetchResponse:
    """Fetch IPO research for many symbols; skips already-fetched when skip_fetched=True."""
    results: list[IpoBatchFetchResultItem] = []
    fetched_count = failed_count = skipped_count = 0

    symbols = [_normalize_symbol(i.symbol) for i in items]
    status_resp = get_ipo_llm_status_map(symbols)
    status_by_symbol = {s.symbol: s.status for s in status_resp.statuses}

    for item in items:
        symbol = _normalize_symbol(item.symbol)
        if skip_fetched and status_by_symbol.get(symbol) == "fetched":
            results.append(IpoBatchFetchResultItem(symbol=symbol, status="skipped"))
            skipped_count += 1
            continue

        try:
            fetch_and_store_ipo_research(
                symbol,
                company_name=item.company_name,
                force_refresh=False,
            )
            results.append(IpoBatchFetchResultItem(symbol=symbol, status="fetched"))
            fetched_count += 1
            status_by_symbol[symbol] = "fetched"
        except Exception as exc:
            results.append(
                IpoBatchFetchResultItem(symbol=symbol, status="failed", error=str(exc))
            )
            failed_count += 1
            status_by_symbol[symbol] = "failed"

    return IpoBatchFetchResponse(
        results=results,
        fetched_count=fetched_count,
        failed_count=failed_count,
        skipped_count=skipped_count,
    )
