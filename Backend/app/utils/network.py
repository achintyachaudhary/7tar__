"""Bypass IDE/sandbox HTTP proxies for Yahoo Finance and NSE requests."""

import os
from contextlib import contextmanager

_PROXY_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "http_proxy",
    "https_proxy",
    "ALL_PROXY",
    "all_proxy",
    "GIT_HTTP_PROXY",
    "GIT_HTTPS_PROXY",
    "SOCKS_PROXY",
    "SOCKS5_PROXY",
    "socks_proxy",
    "socks5_proxy",
)

_EXTRA_NO_PROXY = (
    "finance.yahoo.com",
    "query1.finance.yahoo.com",
    "query2.finance.yahoo.com",
    "www.nseindia.com",
    "nsearchives.nseindia.com",
)


def configure_market_data_network() -> None:
    """
    Remove proxy env vars that Cursor/sandbox injects (often returns 403 for Yahoo).
    Call once at application startup.
    """
    for key in _PROXY_KEYS:
        os.environ.pop(key, None)

    existing = os.environ.get("NO_PROXY") or os.environ.get("no_proxy") or ""
    parts = {p.strip() for p in existing.split(",") if p.strip()}
    parts.update(_EXTRA_NO_PROXY)
    parts.update({"127.0.0.1", "localhost", "::1"})
    merged = ",".join(sorted(parts))
    os.environ["NO_PROXY"] = merged
    os.environ["no_proxy"] = merged


@contextmanager
def without_proxy():
    """Temporarily clear proxy variables for a single operation."""
    saved = {k: os.environ[k] for k in _PROXY_KEYS if k in os.environ}
    for key in saved:
        del os.environ[key]
    try:
        yield
    finally:
        os.environ.update(saved)


def make_requests_session() -> "requests.Session":
    """requests.Session that ignores HTTP_PROXY from the environment."""
    import requests

    session = requests.Session()
    session.trust_env = False
    return session
