import logging

from app.db import stockdata
from app.llm import ollama_client
from app.services import rag_service, searxng_client
from app.services.prompt_builder import build_freeform_prompt, build_stock_prompt

log = logging.getLogger("lm.stock")


def _web_search(query: str, categories: str = "general") -> list[dict]:
    """Best-effort live web search; never raises into the request flow."""
    try:
        return searxng_client.search(query, categories=categories)
    except Exception as exc:
        log.warning("web search skipped: %s", exc)
        return []


def gather_stock_data(symbol: str) -> dict:
    prices = stockdata.get_recent_prices(symbol)
    return {
        "profile": stockdata.get_profile(symbol),
        "snapshot": stockdata.get_snapshot(symbol),
        "prices": prices,
        "price_summary": stockdata.compute_price_summary(prices),
        "financials": stockdata.get_financials(symbol),
        "holdings": stockdata.get_holdings(symbol),
    }


def analyze_stock(symbol: str, question: str | None = None, use_web: bool = False) -> dict:
    symbol = symbol.upper().strip()
    data = gather_stock_data(symbol)

    query = question or f"{symbol} stock outlook news results"
    # news payloads store bare tickers (RELIANCE), symbols carry exchange suffix (RELIANCE.NS)
    docs = rag_service.search_context(query, ticker=symbol.split(".")[0])

    name = (data.get("profile") or {}).get("company_name") or symbol.split(".")[0]
    web = _web_search(f"{name} stock {question or 'latest news price target'}") if use_web else []

    prompt = build_stock_prompt(symbol, data, docs, question, web_results=web)
    llm = ollama_client.chat(prompt)

    return {
        "symbol": symbol,
        "report": llm["answer"],
        "reasoning": llm["reasoning"],
        "data": {k: v for k, v in data.items() if k != "prices"},
        "prices": data["prices"][-120:],
        "news_used": docs,
        "web_used": web,
    }


def ask_freeform(question: str, use_web: bool = True) -> dict:
    docs = rag_service.search_context(question)
    web = _web_search(question) if use_web else []
    llm = ollama_client.chat(build_freeform_prompt(question, docs, web_results=web))
    return {
        "question": question,
        "answer": llm["answer"],
        "reasoning": llm["reasoning"],
        "news_used": docs,
        "web_used": web,
    }
