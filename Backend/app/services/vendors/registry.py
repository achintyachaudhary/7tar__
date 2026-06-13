"""Capability → vendor registry.

Each externally sourced feature is a *capability* with an active vendor,
overridable per capability via env var ``VENDOR_<CAPABILITY>`` (uppercased),
e.g. ``VENDOR_FUNDAMENTALS=yfinance``. Feature code asks the registry which
vendor is active instead of hardcoding a source, so swapping vendors is a
config change plus (at most) a new client in this package.

GET /api/vendors serves this map to the UI's "Data sources" panel.
"""

from __future__ import annotations

import os
from typing import Any

from app.services.vendors import upstox

# kind: api (token-authenticated REST), scrape (headless browser), lib (client library)
VENDOR_INFO: dict[str, dict[str, str]] = {
    "upstox": {"label": "Upstox Analytics API", "kind": "api"},
    "yfinance": {"label": "Yahoo Finance (yfinance)", "kind": "lib"},
    "nse": {"label": "NSE India (filings & archives)", "kind": "api"},
    "investorgain": {"label": "InvestorGain (scraper)", "kind": "scrape"},
    "chittorgarh": {"label": "Chittorgarh (scraper)", "kind": "scrape"},
    "gemini": {"label": "Google Gemini (LLM)", "kind": "api"},
}

# capability id → {label, description, default vendor, alternatives}
CAPABILITIES: dict[str, dict[str, Any]] = {
    "market_indices": {
        "label": "Market indices (NIFTY / BANKNIFTY)",
        "description": "Topbar ticker quotes — real-time LTP during the session; yfinance keeps the 1Y charts.",
        "default": "upstox",
        "options": ["upstox", "yfinance"],
    },
    "price_history": {
        "label": "Daily OHLCV backfill (Day Scan)",
        "description": "stock_prices_daily history powering every screener.",
        "default": "yfinance",
        "options": ["yfinance", "upstox"],
    },
    "live_quotes": {
        "label": "Live quotes (Portfolio engine + tick feed)",
        "description": "Real-time batch LTP for paper trades and the websocket tick feed.",
        "default": "upstox",
        "options": ["upstox", "yfinance"],
    },
    "fundamentals": {
        "label": "Fundamentals (revenue & profit)",
        "description": "Quarterly income statements for Golden/Weekly screeners and insights.",
        "default": "upstox",
        "options": ["upstox", "yfinance"],
    },
    "shareholding": {
        "label": "Shareholding pattern",
        "description": "Promoter / FII / DII / retail percentages and history.",
        "default": "upstox",
        "options": ["upstox", "nse"],
    },
    "news": {
        "label": "Stock news (followed symbols)",
        "description": "News feed for stocks you follow, by instrument key.",
        "default": "upstox",
        "options": ["upstox"],
    },
    "ipo_catalog": {
        "label": "IPO catalog & verification",
        "description": "Authoritative IPO list (symbol, ISIN, price band, dates) used to verify scraped rows.",
        "default": "upstox",
        "options": ["upstox"],
    },
    "ipo_gmp": {
        "label": "IPO grey-market premium",
        "description": "GMP and fire ratings (no official source exists — scraped).",
        "default": "investorgain",
        "options": ["investorgain"],
    },
    "ipo_subscription": {
        "label": "IPO live subscription",
        "description": "QIB / NII / Retail bidding multiples during the issue.",
        "default": "chittorgarh",
        "options": ["chittorgarh", "upstox"],
    },
    "ipo_llm_research": {
        "label": "IPO LLM research",
        "description": "Generated IPO subscription research notes.",
        "default": "gemini",
        "options": ["gemini"],
    },
}

# Capabilities that need the Upstox token to actually work
_NEEDS_UPSTOX_TOKEN = {"fundamentals", "shareholding", "news", "ipo_catalog"}


def active_vendor(capability: str) -> str:
    cap = CAPABILITIES.get(capability)
    if cap is None:
        raise KeyError(f"Unknown capability: {capability}")
    override = os.getenv(f"VENDOR_{capability.upper()}", "").strip().lower()
    if override and override in cap["options"]:
        return override
    return cap["default"]


def use_upstox(capability: str) -> bool:
    """True when the capability routes to Upstox AND a token is configured."""
    return active_vendor(capability) == "upstox" and upstox.is_configured()


def list_feature_vendors() -> list[dict[str, Any]]:
    """Feature → vendor map for the UI, with live config status."""
    token_ok = upstox.is_configured()
    out: list[dict[str, Any]] = []
    for cap_id, cap in CAPABILITIES.items():
        vendor = active_vendor(cap_id)
        info = VENDOR_INFO.get(vendor, {"label": vendor, "kind": "api"})
        degraded = (
            vendor == "upstox" and cap_id in _NEEDS_UPSTOX_TOKEN and not token_ok
        )
        out.append(
            {
                "capability": cap_id,
                "label": cap["label"],
                "description": cap["description"],
                "vendor": vendor,
                "vendor_label": info["label"],
                "vendor_kind": info["kind"],
                "options": cap["options"],
                "env_override": f"VENDOR_{cap_id.upper()}",
                "degraded": degraded,
                "note": "Upstox token missing — falls back where possible" if degraded else None,
            }
        )
    return out
