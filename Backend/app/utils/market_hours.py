"""NSE market-session clock (IST), shared by quotes and engines.

Session phases, Monday–Friday:
- pre-open  09:00–09:15 IST — order collection till ~09:08, then price
  discovery; indices and stocks print their first prices from ~09:07.
- open      09:15–15:30 IST — continuous (normal) trading.
- closed    everything else.

``is_nse_market_open`` covers only the continuous session (entries/exits);
``is_nse_data_live`` also covers pre-open, and gates everything that merely
consumes prices (tick feed, quote caches, UI freshness). Exchange holidays are
not modelled — on a holiday the app behaves like a quiet trading day.
"""

from __future__ import annotations

from datetime import datetime, time as dt_time, timedelta, timezone
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

NSE_PRE_OPEN = dt_time(9, 0)
NSE_OPEN = dt_time(9, 15)
NSE_CLOSE = dt_time(15, 30)


def now_ist(ref: datetime | None = None) -> datetime:
    base = ref or datetime.now(timezone.utc)
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    return base.astimezone(IST)


def nse_session_phase(ref: datetime | None = None) -> str:
    """Current NSE session phase: ``"pre_open"``, ``"open"`` or ``"closed"``."""
    ist = now_ist(ref)
    if ist.weekday() >= 5:  # Sat/Sun
        return "closed"
    t = ist.time()
    if NSE_PRE_OPEN <= t < NSE_OPEN:
        return "pre_open"
    if NSE_OPEN <= t <= NSE_CLOSE:
        return "open"
    return "closed"


def is_nse_market_open(ref: datetime | None = None) -> bool:
    """Continuous trading session only — the window where entries/exits happen."""
    return nse_session_phase(ref) == "open"


def is_nse_data_live(ref: datetime | None = None) -> bool:
    """Pre-open or continuous session — live prices exist on the exchange."""
    return nse_session_phase(ref) != "closed"


def current_session_date(ref: datetime | None = None):
    """Date of the session the latest traded price belongs to.

    From pre-open onward that's today (a 09:07 first print belongs to today's
    session, so its previous close is yesterday's bar); outside hours it's the
    date of the last completed close — the correct anchor when picking a
    'previous close' for day-change math (a calendar-today check breaks after
    midnight and when cached bars lag a day).
    """
    if is_nse_data_live(ref):
        return now_ist(ref).date()
    return last_nse_close(ref).astimezone(IST).date()


def last_nse_close(ref: datetime | None = None) -> datetime:
    """UTC datetime of the most recently *completed* session close (15:30 IST).

    Data fetched before this moment predates the final close — e.g. a quote
    cached at 15:20 must not be served as "at close" after 15:30.
    """
    ist = now_ist(ref)
    day = ist.date()
    while True:
        if day.weekday() < 5:
            close_dt = datetime.combine(day, NSE_CLOSE, tzinfo=IST)
            if close_dt <= ist:
                return close_dt.astimezone(timezone.utc)
        day -= timedelta(days=1)
