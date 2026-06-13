"""Live web search via a local SearXNG instance (JSON API).

SearXNG ships with the JSON output format DISABLED by default. To enable it,
add to the instance's settings.yml:

    search:
      formats:
        - html
        - json

then restart SearXNG. Until then status()['json'] is False and search()
raises, but the rest of the app keeps working (web context is optional).
"""

import logging

import requests

from app.config import SEARXNG_URL, SEARXNG_TIMEOUT, WEB_MAX_RESULTS

log = logging.getLogger("lm.searxng")

_HEADERS = {"User-Agent": "Mozilla/5.0 (gcc lm stock-ai)"}


def search(query: str, max_results: int = WEB_MAX_RESULTS, categories: str = "general") -> list[dict]:
    """Return a list of {title, url, content, engine, published} for the query."""
    resp = requests.get(
        f"{SEARXNG_URL}/search",
        params={"q": query, "format": "json", "categories": categories, "language": "en"},
        headers=_HEADERS,
        timeout=SEARXNG_TIMEOUT,
    )
    if resp.status_code == 403:
        raise RuntimeError(
            "SearXNG returned 403 for the JSON API — enable it in settings.yml "
            "(search.formats: [html, json]) and restart SearXNG."
        )
    resp.raise_for_status()
    results = resp.json().get("results", [])
    out = []
    for r in results[:max_results]:
        out.append({
            "title": (r.get("title") or "").strip(),
            "url": r.get("url"),
            "content": (r.get("content") or "").strip(),
            "engine": r.get("engine"),
            "published": r.get("publishedDate"),
        })
    return out


def status() -> dict:
    """Lightweight reachability + JSON-enabled check, never raises."""
    info = {"url": SEARXNG_URL, "available": False, "json": False, "reason": None}
    try:
        root = requests.get(SEARXNG_URL, headers=_HEADERS, timeout=6)
        info["available"] = root.ok
    except Exception as exc:
        info["reason"] = f"unreachable: {exc}"
        return info
    try:
        r = requests.get(
            f"{SEARXNG_URL}/search",
            params={"q": "ping", "format": "json"},
            headers=_HEADERS,
            timeout=SEARXNG_TIMEOUT,
        )
        if r.status_code == 200 and "json" in (r.headers.get("content-type") or ""):
            info["json"] = True
        elif r.status_code == 403:
            info["reason"] = "JSON API disabled (403) — add 'json' to search.formats in settings.yml"
        else:
            info["reason"] = f"unexpected status {r.status_code}"
    except Exception as exc:
        info["reason"] = f"json check failed: {exc}"
    return info
