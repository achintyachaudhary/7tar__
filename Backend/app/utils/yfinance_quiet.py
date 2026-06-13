"""Reduce yfinance stderr noise (delisted / no timezone warnings)."""

from __future__ import annotations

import logging
import os
import sys
from contextlib import contextmanager


def configure_yfinance_logging() -> None:
    """Call once at app startup."""
    for name in ("yfinance", "yfinance.base", "yfinance.scrapers", "yfinance.scrapers.quote"):
        logging.getLogger(name).setLevel(logging.ERROR)


@contextmanager
def quiet_yfinance():
    """Suppress yfinance log + stderr spam during bulk IPO price fetches."""
    loggers = [
        logging.getLogger(n)
        for n in ("yfinance", "yfinance.base", "yfinance.scrapers", "yfinance.scrapers.quote")
    ]
    prior = [(lg, lg.level) for lg in loggers]
    old_stderr = sys.stderr
    try:
        for lg, _ in prior:
            lg.setLevel(logging.CRITICAL)
        with open(os.devnull, "w", encoding="utf-8") as devnull:
            sys.stderr = devnull
            yield
    finally:
        sys.stderr = old_stderr
        for lg, level in prior:
            lg.setLevel(level)
