"""IPO tracker — reads shared ipo_listings DB (same as IPO Research)."""

from datetime import datetime, timezone

from app.models import IpoListing, IpoTrackResponse
from app.services.ipo_catalog import DEFAULT_TRACKER_MONTHS, list_ipo_listings_for_api, sync_ipo_catalog


def track_recent_ipos(months: int = 2, refresh: bool = False) -> IpoTrackResponse:
    if months not in (1, 2, 6):
        months = DEFAULT_TRACKER_MONTHS

    rows = list_ipo_listings_for_api(months=months)
    if refresh or len(rows) == 0:
        sync_ipo_catalog(months=months, force_refresh=refresh, batch_size=80)
        rows = list_ipo_listings_for_api(months=months)
    with_data = sum(1 for r in rows if r.get("current_price") is not None)
    listings = [IpoListing(**row) for row in rows]

    return IpoTrackResponse(
        scanned_at=datetime.now(timezone.utc).isoformat(),
        months=months,
        total_listed=len(listings),
        with_market_data=with_data,
        results=listings,
    )
