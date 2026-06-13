"""CRUD helpers for all ORM tables."""

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session


def _iso_utc(dt: datetime | None) -> str | None:
    """Serialize a datetime as a timezone-aware UTC ISO string.

    SQLite drops tzinfo on read, so naive values (which we always store as UTC)
    are treated as UTC here. This lets the frontend convert to IST correctly.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()

from app.db.models import (
    DashboardWidget,
    FinancialCache,
    HoldingsCache,
    IpoListing,
    IpoLlmResearch,
    IpoMlFeatureRow,
    IpoResearchRun,
    MarketIndexCache,
    StockProfile,
    UserPreferences,
)

CACHE_STALE_DAYS = 90


def _is_stale(dt: datetime | None) -> bool:
    if dt is None:
        return True
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - dt > timedelta(days=CACHE_STALE_DAYS)


# ── StockProfile ──────────────────────────────────────────────────────────────

def get_profile(db: Session, symbol: str) -> StockProfile | None:
    return db.get(StockProfile, symbol.upper())


def profile_is_fresh(db: Session, symbol: str) -> bool:
    row = get_profile(db, symbol.upper())
    return row is not None and not _is_stale(row.last_updated)


def upsert_profile(db: Session, symbol: str, data: dict[str, Any]) -> StockProfile:
    symbol = symbol.upper()
    row = db.get(StockProfile, symbol)
    if row is None:
        row = StockProfile(symbol=symbol)
        db.add(row)
    for k, v in data.items():
        setattr(row, k, v)
    row.last_updated = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row


# ── HoldingsCache ─────────────────────────────────────────────────────────────

def get_holdings(db: Session, symbol: str) -> HoldingsCache | None:
    return db.get(HoldingsCache, symbol.upper())


def holdings_is_fresh(db: Session, symbol: str) -> bool:
    row = get_holdings(db, symbol.upper())
    return row is not None and not _is_stale(row.last_fetched)


def upsert_holdings(
    db: Session,
    symbol: str,
    latest: dict[str, Any],
    history: list[dict[str, Any]],
) -> HoldingsCache:
    symbol = symbol.upper()
    row = db.get(HoldingsCache, symbol)
    if row is None:
        row = HoldingsCache(symbol=symbol)
        db.add(row)
    row.promoter_pct = latest.get("promoter_holding_pct")
    row.fii_pct = latest.get("fii_holding_pct")
    row.dii_pct = latest.get("dii_holding_pct")
    row.public_pct = latest.get("public_holding_pct")
    row.retail_pct = latest.get("retail_and_others_pct")
    row.as_of = latest.get("as_of")
    row.history_json = json.dumps(history)
    row.last_fetched = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row


def get_holdings_history(db: Session, symbol: str) -> list[dict[str, Any]]:
    row = get_holdings(db, symbol.upper())
    if row is None or not row.history_json:
        return []
    try:
        return json.loads(row.history_json)
    except (json.JSONDecodeError, TypeError):
        return []


# ── FinancialCache ────────────────────────────────────────────────────────────

def financials_are_fresh(db: Session, symbol: str) -> bool:
    symbol = symbol.upper()
    rows = (
        db.query(FinancialCache)
        .filter(FinancialCache.symbol == symbol)
        .limit(1)
        .all()
    )
    if not rows:
        return False
    return not _is_stale(rows[0].last_fetched)


def upsert_financials(
    db: Session,
    symbol: str,
    periods: list[dict[str, Any]],
    is_quarterly: bool,
) -> None:
    symbol = symbol.upper()
    db.query(FinancialCache).filter(
        FinancialCache.symbol == symbol,
        FinancialCache.is_quarterly == is_quarterly,
    ).delete()

    now = datetime.now(timezone.utc)
    for p in periods:
        row = FinancialCache(
            symbol=symbol,
            period_label=p.get("label", ""),
            is_quarterly=is_quarterly,
            revenue_cr=p.get("revenue_cr"),
            profit_cr=p.get("profit_cr"),
            period_date=p.get("period"),
            last_fetched=now,
        )
        db.add(row)
    db.commit()


def get_financials_rows(
    db: Session, symbol: str, is_quarterly: bool
) -> list[dict[str, Any]]:
    symbol = symbol.upper()
    rows = (
        db.query(FinancialCache)
        .filter(
            FinancialCache.symbol == symbol,
            FinancialCache.is_quarterly == is_quarterly,
        )
        .order_by(FinancialCache.period_date)
        .all()
    )
    return [
        {
            "period": r.period_date,
            "label": r.period_label,
            "revenue_cr": r.revenue_cr,
            "profit_cr": r.profit_cr,
        }
        for r in rows
    ]


# ── UserPreferences ───────────────────────────────────────────────────────────

def get_pref(db: Session, key: str) -> str | None:
    row = db.get(UserPreferences, key)
    return row.value if row else None


def set_pref(db: Session, key: str, value: str) -> None:
    row = db.get(UserPreferences, key)
    if row is None:
        row = UserPreferences(key=key, value=value)
        db.add(row)
    else:
        row.value = value
    db.commit()


def get_all_prefs(db: Session) -> dict[str, str]:
    rows = db.query(UserPreferences).all()
    return {r.key: r.value for r in rows}


# ── DashboardWidget ───────────────────────────────────────────────────────────

def list_widgets(db: Session) -> list[dict[str, Any]]:
    rows = db.query(DashboardWidget).order_by(DashboardWidget.position).all()
    return [
        {
            "id": r.id,
            "widget_type": r.widget_type,
            "size": r.size,
            "position": r.position,
            "config": json.loads(r.config_json) if r.config_json else {},
        }
        for r in rows
    ]


# ── MarketIndexCache ──────────────────────────────────────────────────────────

def get_market_index(db: Session, index_id: str) -> MarketIndexCache | None:
    return db.get(MarketIndexCache, index_id.lower())


def upsert_market_index(
    db: Session,
    index_id: str,
    display_name: str,
    yf_symbol: str,
    last_value: float,
    change_abs: float,
    change_pct: float,
    quote_updated_at: datetime,
    bars_json: str | None = None,
    bars_updated_at: datetime | None = None,
) -> MarketIndexCache:
    """Quote-only updates leave the cached chart bars untouched."""
    index_id = index_id.lower()
    row = db.get(MarketIndexCache, index_id)
    if row is None:
        row = MarketIndexCache(index_id=index_id)
        db.add(row)
    row.display_name = display_name
    row.yf_symbol = yf_symbol
    row.last_value = last_value
    row.change_abs = change_abs
    row.change_pct = change_pct
    row.quote_updated_at = quote_updated_at
    if bars_json is not None:
        row.bars_json = bars_json
    if bars_updated_at is not None:
        row.bars_updated_at = bars_updated_at
    db.commit()
    db.refresh(row)
    return row


# ── IpoListing (shared Tracker + Research) ────────────────────────────────────

def get_ipo_listing(db: Session, symbol: str) -> IpoListing | None:
    return db.get(IpoListing, symbol.upper())


def upsert_ipo_listing(db: Session, symbol: str, **fields: Any) -> IpoListing:
    symbol = symbol.upper()
    row = db.get(IpoListing, symbol)
    if row is None:
        row = IpoListing(symbol=symbol, listing_date=fields.get("listing_date", ""))
        db.add(row)
    for key, value in fields.items():
        if hasattr(row, key):
            setattr(row, key, value)
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row


def list_ipo_listings(
    db: Session,
    *,
    symbols: set[str] | None = None,
    ml_ready_only: bool = False,
) -> list[IpoListing]:
    q = db.query(IpoListing)
    if symbols:
        q = q.filter(IpoListing.symbol.in_([s.upper() for s in symbols]))
    if ml_ready_only:
        q = q.filter(IpoListing.ml_status == "ready")
    return q.order_by(IpoListing.listing_date.desc()).all()


def latest_ipo_listing_update(db: Session) -> datetime | None:
    row = db.query(IpoListing).order_by(IpoListing.updated_at.desc()).first()
    return row.updated_at if row else None


def ipo_listing_to_dict(row: IpoListing) -> dict[str, Any]:
    market_status = row.market_status or "pending"
    status = (
        "no_market_data"
        if market_status == "no_market_data"
        else ("listed" if row.current_price is not None else "no_market_data")
    )
    return {
        "symbol": row.symbol,
        "company_name": row.company_name or row.symbol,
        "security_type": row.security_type or "",
        "ipo_start_date": row.ipo_start_date or "",
        "ipo_end_date": row.ipo_end_date or "",
        "listing_date": row.listing_date,
        "listing_date_display": row.listing_date_display or row.listing_date,
        "issue_price": row.issue_price,
        "price_range": row.price_range or "",
        "yf_symbol": row.yf_symbol,
        "listing_open": row.listing_open,
        "listing_close": row.listing_close,
        "listing_high": row.listing_high,
        "current_price": row.current_price,
        "listing_day_gain_pct": row.listing_day_gain_pct,
        "gain_vs_issue_pct": row.gain_vs_issue_pct,
        "gain_vs_listing_close_pct": row.gain_vs_listing_close_pct,
        "gain_listing_open_to_current_pct": row.gain_listing_open_to_current_pct,
        "status": status,
    }


# ── IpoMlFeatureRow (legacy) ──────────────────────────────────────────────────

def get_ipo_ml_row(db: Session, symbol: str) -> IpoMlFeatureRow | None:
    return db.get(IpoMlFeatureRow, symbol.upper())


def upsert_ipo_ml_row(
    db: Session,
    symbol: str,
    listing_date: str,
    company_name: str,
    features_json: str,
    targets_json: str,
    built_at: datetime | None = None,
    enrichment_status: str = "ready",
) -> IpoMlFeatureRow:
    symbol = symbol.upper()
    row = db.get(IpoMlFeatureRow, symbol)
    if row is None:
        row = IpoMlFeatureRow(symbol=symbol)
        db.add(row)
    row.listing_date = listing_date
    row.company_name = company_name
    row.features_json = features_json
    row.targets_json = targets_json
    row.enrichment_status = enrichment_status
    if built_at:
        row.built_at = built_at
    db.commit()
    db.refresh(row)
    return row


def list_ipo_ml_rows(db: Session, *, ready_only: bool = True) -> list[IpoMlFeatureRow]:
    q = db.query(IpoMlFeatureRow)
    if ready_only:
        q = q.filter(IpoMlFeatureRow.enrichment_status == "ready")
    return q.order_by(IpoMlFeatureRow.listing_date.desc()).all()


def count_ipo_ml_rows(db: Session, *, ready_only: bool = False) -> int:
    q = db.query(IpoMlFeatureRow)
    if ready_only:
        q = q.filter(IpoMlFeatureRow.enrichment_status == "ready")
    return q.count()


def latest_ipo_ml_built_at(db: Session) -> datetime | None:
    row = db.query(IpoMlFeatureRow).order_by(IpoMlFeatureRow.built_at.desc()).first()
    return row.built_at if row else None


# ── IpoResearchRun ────────────────────────────────────────────────────────────

def create_ipo_research_run(
    db: Session,
    algorithm: str,
    params_json: str | None = None,
) -> IpoResearchRun:
    run = IpoResearchRun(algorithm=algorithm, status="running", params_json=params_json)
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def update_ipo_research_run(
    db: Session,
    run_id: int,
    *,
    status: str,
    metrics_json: str | None = None,
    insights_json: str | None = None,
    summary_text: str | None = None,
    sample_count: int | None = None,
    error_message: str | None = None,
) -> IpoResearchRun | None:
    run = db.get(IpoResearchRun, run_id)
    if run is None:
        return None
    run.status = status
    if metrics_json is not None:
        run.metrics_json = metrics_json
    if insights_json is not None:
        run.insights_json = insights_json
    if summary_text is not None:
        run.summary_text = summary_text
    if sample_count is not None:
        run.sample_count = sample_count
    if error_message is not None:
        run.error_message = error_message
    if status in ("completed", "failed"):
        run.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(run)
    return run


def list_ipo_research_runs(db: Session, limit: int = 50) -> list[IpoResearchRun]:
    return (
        db.query(IpoResearchRun)
        .order_by(IpoResearchRun.created_at.desc())
        .limit(limit)
        .all()
    )


def get_ipo_research_run(db: Session, run_id: int) -> IpoResearchRun | None:
    return db.get(IpoResearchRun, run_id)


# ── IpoLlmResearch ────────────────────────────────────────────────────────────

def get_ipo_llm_research(db: Session, symbol: str) -> IpoLlmResearch | None:
    return db.get(IpoLlmResearch, symbol.upper())


def upsert_ipo_llm_research(
    db: Session,
    symbol: str,
    provider: str,
    payload_json: str,
    fetched_at: datetime | None = None,
) -> IpoLlmResearch:
    symbol = symbol.upper()
    row = db.get(IpoLlmResearch, symbol)
    if row is None:
        row = IpoLlmResearch(symbol=symbol)
        db.add(row)
    row.provider = provider
    row.status = "fetched"
    row.payload_json = payload_json
    row.error_message = None
    if fetched_at:
        row.fetched_at = fetched_at
    db.commit()
    db.refresh(row)
    return row


def upsert_ipo_llm_failed(
    db: Session,
    symbol: str,
    provider: str,
    error_message: str,
) -> IpoLlmResearch:
    symbol = symbol.upper()
    row = db.get(IpoLlmResearch, symbol)
    if row is None:
        row = IpoLlmResearch(symbol=symbol)
        db.add(row)
    row.provider = provider
    row.status = "failed"
    row.payload_json = row.payload_json or "{}"
    row.error_message = error_message[:2000]
    row.fetched_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row


def list_ipo_llm_status(
    db: Session,
    symbols: list[str],
) -> dict[str, IpoLlmResearch | None]:
    normalized = [s.upper().replace(".NS", "").strip() for s in symbols if s]
    if not normalized:
        return {}
    rows = (
        db.query(IpoLlmResearch)
        .filter(IpoLlmResearch.symbol.in_(normalized))
        .all()
    )
    by_symbol = {r.symbol: r for r in rows}
    return {s: by_symbol.get(s) for s in normalized}


def save_widgets(db: Session, widgets: list[dict[str, Any]]) -> None:
    db.query(DashboardWidget).delete()
    for i, w in enumerate(widgets):
        row = DashboardWidget(
            widget_type=w["widget_type"],
            size=w.get("size", "md"),
            position=i,
            config_json=json.dumps(w.get("config", {})),
        )
        db.add(row)
    db.commit()


# ── StockUniverse ─────────────────────────────────────────────────────────────

def count_stock_universe(db: Session, active_only: bool = True) -> int:
    """Count total stocks in the universe table."""
    from app.db.models import StockUniverse
    q = db.query(StockUniverse)
    if active_only:
        q = q.filter(StockUniverse.is_active == True)
    return q.count()


def list_stock_universe(db: Session, active_only: bool = True) -> list[str]:
    """Return list of symbols from stock universe."""
    from app.db.models import StockUniverse
    q = db.query(StockUniverse.symbol)
    if active_only:
        q = q.filter(StockUniverse.is_active == True)
    return [row[0] for row in q.all()]


def search_stock_suggestions(
    db: Session,
    query: str,
    *,
    limit: int = 12,
) -> list[dict[str, Any]]:
    """Return NSE symbols matching a symbol or company-name prefix/substring."""
    from sqlalchemy import func, or_

    from app.db.models import DayScanSnapshot, StockProfile, StockUniverse

    q = query.strip()
    if not q:
        return []

    q_upper = q.upper().replace(".NS", "").replace(".BO", "")
    sym_pattern = f"%{q_upper}%"
    name_pattern = f"%{q}%"

    rows = (
        db.query(DayScanSnapshot, StockProfile.company_name)
        .join(StockUniverse, DayScanSnapshot.symbol == StockUniverse.symbol)
        .outerjoin(StockProfile, DayScanSnapshot.symbol == StockProfile.symbol)
        .filter(StockUniverse.is_active == True)
        .filter(
            or_(
                func.upper(DayScanSnapshot.symbol).like(sym_pattern),
                DayScanSnapshot.company_name.like(name_pattern),
                StockProfile.company_name.like(name_pattern),
            )
        )
        .limit(max(limit * 4, limit))
        .all()
    )

    def _rank(item: tuple[Any, Any]) -> tuple[int, str]:
        snap, profile_name = item
        sym_base = snap.symbol.upper().replace(".NS", "").replace(".BO", "")
        company = snap.company_name or profile_name or sym_base
        if sym_base == q_upper:
            return (0, sym_base)
        if sym_base.startswith(q_upper):
            return (1, sym_base)
        if q_upper in sym_base:
            return (2, sym_base)
        if company and q.lower() in company.lower():
            return (3, sym_base)
        return (4, sym_base)

    rows.sort(key=_rank)

    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for snap, profile_name in rows:
        if snap.symbol in seen:
            continue
        seen.add(snap.symbol)
        company = snap.company_name or profile_name or snap.symbol.replace(".NS", "")
        out.append({
            "symbol": snap.symbol,
            "company_name": company,
            "last_price": snap.last_price,
        })
        if len(out) >= limit:
            break
    return out


def bulk_upsert_stock_universe(db: Session, symbols: list[str]) -> int:
    """Bulk insert/update stock universe from a symbol list. Returns count inserted."""
    from app.db.models import StockUniverse
    inserted = 0
    for symbol in symbols:
        existing = db.get(StockUniverse, symbol)
        if existing is None:
            company_name = symbol.replace(".NS", "").replace(".BO", "")
            db.add(StockUniverse(symbol=symbol, company_name=company_name, is_active=True))
            inserted += 1
        else:
            existing.is_active = True
    db.commit()
    return inserted


def list_stock_universe_with_filters(
    db: Session,
    active_only: bool = True,
    min_market_cap_cr: float | None = None,
    max_market_cap_cr: float | None = None,
) -> list[str]:
    """
    Return list of symbols from stock universe with optional market cap filter.
    Market cap values are in crores (Cr). Uses day_scan_snapshots for market cap
    (populated by Day Scan fetch) since stock_profiles rarely has cap data.
    """
    from app.db.models import DayScanSnapshot, StockUniverse

    q = db.query(StockUniverse.symbol)

    if active_only:
        q = q.filter(StockUniverse.is_active == True)

    if min_market_cap_cr is not None or max_market_cap_cr is not None:
        q = q.join(DayScanSnapshot, StockUniverse.symbol == DayScanSnapshot.symbol)
        q = q.filter(DayScanSnapshot.market_cap_cr.isnot(None))

        if min_market_cap_cr is not None:
            q = q.filter(DayScanSnapshot.market_cap_cr >= min_market_cap_cr)
        if max_market_cap_cr is not None:
            q = q.filter(DayScanSnapshot.market_cap_cr <= max_market_cap_cr)

    return [row[0] for row in q.distinct().all()]


def count_listing_fetched(db: Session, active_only: bool = True) -> int:
    from app.db.models import StockUniverse
    q = db.query(StockUniverse).filter(StockUniverse.data_from_listing == True)
    if active_only:
        q = q.filter(StockUniverse.is_active == True)
    return q.count()


def list_symbols_pending_listing_fetch(db: Session) -> list[str]:
    from app.db.models import StockUniverse
    rows = (
        db.query(StockUniverse.symbol)
        .filter(
            StockUniverse.is_active == True,
            StockUniverse.data_from_listing == False,
        )
        .order_by(StockUniverse.symbol)
        .all()
    )
    return [r[0] for r in rows]


def mark_data_from_listing(
    db: Session,
    symbol: str,
    listing_date: str | None = None,
) -> None:
    from app.db.models import StockUniverse
    symbol = symbol.upper()
    row = db.get(StockUniverse, symbol)
    if row is None:
        row = StockUniverse(symbol=symbol, company_name=symbol.replace(".NS", ""))
        db.add(row)
    row.data_from_listing = True
    if listing_date:
        row.listing_date = listing_date
    row.last_scanned_at = datetime.now(timezone.utc)
    db.commit()


# ── StockPriceDaily ───────────────────────────────────────────────────────────

def get_latest_price_date(db: Session, symbol: str) -> str | None:
    from app.db.models import StockPriceDaily
    row = (
        db.query(StockPriceDaily.trade_date)
        .filter(StockPriceDaily.symbol == symbol.upper())
        .order_by(StockPriceDaily.trade_date.desc())
        .first()
    )
    return row[0] if row else None


def get_earliest_price_date(db: Session, symbol: str) -> str | None:
    from app.db.models import StockPriceDaily
    row = (
        db.query(StockPriceDaily.trade_date)
        .filter(StockPriceDaily.symbol == symbol.upper())
        .order_by(StockPriceDaily.trade_date.asc())
        .first()
    )
    return row[0] if row else None


def upsert_daily_prices(db: Session, symbol: str, bars: list[dict[str, Any]]) -> int:
    from app.db.database import engine
    from app.db.models import StockPriceDaily

    if engine.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as dialect_insert
    else:
        from sqlalchemy.dialects.sqlite import insert as dialect_insert

    symbol = symbol.upper()
    if not bars:
        return 0

    # Last bar wins when the API returns duplicate dates in one batch.
    by_date: dict[str, dict[str, Any]] = {}
    for bar in bars:
        trade_date = str(bar["trade_date"])[:10]
        by_date[trade_date] = {**bar, "trade_date": trade_date}
    deduped = list(by_date.values())

    existing_dates = {
        row[0]
        for row in db.query(StockPriceDaily.trade_date)
        .filter(
            StockPriceDaily.symbol == symbol,
            StockPriceDaily.trade_date.in_(list(by_date.keys())),
        )
        .all()
    }

    now = datetime.now(timezone.utc)
    rows = [
        {
            "symbol": symbol,
            "trade_date": bar["trade_date"],
            "open": bar.get("open"),
            "high": bar.get("high"),
            "low": bar.get("low"),
            "close": bar["close"],
            "volume": bar.get("volume"),
            "fetched_at": now,
        }
        for bar in deduped
    ]

    stmt = dialect_insert(StockPriceDaily).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["symbol", "trade_date"],
        set_={
            "open": stmt.excluded.open,
            "high": stmt.excluded.high,
            "low": stmt.excluded.low,
            "close": stmt.excluded.close,
            "volume": stmt.excluded.volume,
            "fetched_at": stmt.excluded.fetched_at,
        },
    )
    db.execute(stmt)
    db.commit()
    return sum(1 for d in by_date if d not in existing_dates)


def get_price_series(db: Session, symbol: str) -> list[tuple[str, float]]:
    from app.db.models import StockPriceDaily
    rows = (
        db.query(StockPriceDaily.trade_date, StockPriceDaily.close)
        .filter(StockPriceDaily.symbol == symbol.upper())
        .order_by(StockPriceDaily.trade_date.asc())
        .all()
    )
    return [(r[0], r[1]) for r in rows]


def get_daily_ohlcv_bars(
    db: Session,
    symbol: str,
    *,
    since_date: date | None = None,
) -> list[dict[str, Any]]:
    """Return stored daily OHLCV bars for a symbol, optionally bounded by date."""
    from app.db.models import StockPriceDaily

    q = (
        db.query(StockPriceDaily)
        .filter(StockPriceDaily.symbol == symbol.upper())
    )
    if since_date is not None:
        cutoff = since_date.isoformat()
        q = q.filter(StockPriceDaily.trade_date >= cutoff)
    rows = q.order_by(StockPriceDaily.trade_date.asc()).all()
    return [
        {
            "time": r.trade_date,
            "open": r.open if r.open is not None else r.close,
            "high": r.high if r.high is not None else r.close,
            "low": r.low if r.low is not None else r.close,
            "close": r.close,
            "volume": r.volume,
        }
        for r in rows
    ]


def snapshot_map(db: Session) -> dict[str, dict[str, Any]]:
    """All day_scan_snapshots keyed by symbol."""
    return {row["symbol"]: row for row in list_day_scan_snapshots(db)}


def bulk_daily_ohlcv_bars(
    db: Session,
    symbols: list[str],
    *,
    since_date: date | None = None,
    chunk_size: int = 400,
) -> dict[str, list[dict[str, Any]]]:
    """Load daily OHLCV for many symbols in batched queries (single connection)."""
    from app.db.models import StockPriceDaily

    syms = sorted({s.upper() for s in symbols})
    out: dict[str, list[dict[str, Any]]] = {}

    for i in range(0, len(syms), chunk_size):
        chunk = syms[i : i + chunk_size]
        q = db.query(StockPriceDaily).filter(StockPriceDaily.symbol.in_(chunk))
        if since_date is not None:
            cutoff = since_date.isoformat()
            q = q.filter(StockPriceDaily.trade_date >= cutoff)
        rows = q.order_by(StockPriceDaily.symbol, StockPriceDaily.trade_date.asc()).all()
        for r in rows:
            out.setdefault(r.symbol, []).append({
                "time": r.trade_date,
                "open": r.open if r.open is not None else r.close,
                "high": r.high if r.high is not None else r.close,
                "low": r.low if r.low is not None else r.close,
                "close": r.close,
                "volume": r.volume,
            })
    return out


def bulk_financials_quarterly(
    db: Session,
    symbols: list[str],
    *,
    chunk_size: int = 400,
) -> dict[str, list[dict[str, Any]]]:
    """Quarterly financial rows keyed by symbol."""
    from app.db.models import FinancialCache

    syms = sorted({s.upper() for s in symbols})
    out: dict[str, list[dict[str, Any]]] = {}

    for i in range(0, len(syms), chunk_size):
        chunk = syms[i : i + chunk_size]
        rows = (
            db.query(FinancialCache)
            .filter(
                FinancialCache.symbol.in_(chunk),
                FinancialCache.is_quarterly == True,
            )
            .order_by(FinancialCache.symbol, FinancialCache.period_date)
            .all()
        )
        for r in rows:
            out.setdefault(r.symbol, []).append({
                "period": r.period_date,
                "label": r.period_label,
                "revenue_cr": r.revenue_cr,
                "profit_cr": r.profit_cr,
            })
    return out


def bulk_holdings_history(
    db: Session,
    symbols: list[str],
    *,
    chunk_size: int = 400,
) -> dict[str, list[dict[str, Any]]]:
    """Shareholding history JSON keyed by symbol."""
    from app.db.models import HoldingsCache

    syms = sorted({s.upper() for s in symbols})
    out: dict[str, list[dict[str, Any]]] = {}

    for i in range(0, len(syms), chunk_size):
        chunk = syms[i : i + chunk_size]
        rows = db.query(HoldingsCache).filter(HoldingsCache.symbol.in_(chunk)).all()
        for r in rows:
            if not r.history_json:
                continue
            try:
                out[r.symbol] = json.loads(r.history_json)
            except (json.JSONDecodeError, TypeError):
                continue
    return out


def profile_map(db: Session, symbols: list[str] | None = None) -> dict[str, dict[str, Any]]:
    """Stock profiles keyed by symbol (optional symbol filter)."""
    from app.db.models import StockProfile

    q = db.query(StockProfile)
    if symbols:
        syms = [s.upper() for s in symbols]
        q = q.filter(StockProfile.symbol.in_(syms))
    out: dict[str, dict[str, Any]] = {}
    for row in q.all():
        out[row.symbol] = {
            "company_name": row.company_name,
            "industry": row.industry,
            "market_cap_cr": row.market_cap_cr,
            "cap_category": row.cap_category,
        }
    return out


# ── DayScanSnapshot ───────────────────────────────────────────────────────────

def upsert_day_scan_snapshot(db: Session, symbol: str, data: dict[str, Any]) -> None:
    from app.db.models import DayScanSnapshot
    symbol = symbol.upper()
    row = db.get(DayScanSnapshot, symbol)
    if row is None:
        row = DayScanSnapshot(symbol=symbol)
        db.add(row)
    for key, value in data.items():
        if hasattr(row, key):
            setattr(row, key, value)
    row.updated_at = datetime.now(timezone.utc)
    db.commit()


def get_day_scan_snapshot(db: Session, symbol: str) -> dict[str, Any] | None:
    from app.db.models import DayScanSnapshot

    row = db.get(DayScanSnapshot, symbol.upper())
    if row is None:
        return None
    return {
        "symbol": row.symbol,
        "company_name": row.company_name or row.symbol.replace(".NS", ""),
        "industry": row.industry,
        "market_cap_cr": row.market_cap_cr,
        "last_price": row.last_price,
    }


def list_day_scan_snapshots(db: Session) -> list[dict[str, Any]]:
    from app.db.models import DayScanSnapshot
    rows = db.query(DayScanSnapshot).order_by(DayScanSnapshot.symbol).all()
    return [
        {
            "symbol": r.symbol,
            "company_name": r.company_name or r.symbol.replace(".NS", ""),
            "industry": r.industry,
            "market_cap_cr": r.market_cap_cr,
            "pe_ratio": r.pe_ratio,
            "roce_pct": r.roce_pct,
            "return_1d_pct": r.return_1d_pct,
            "return_1w_pct": r.return_1w_pct,
            "return_1m_pct": r.return_1m_pct,
            "return_1y_pct": r.return_1y_pct,
            "last_price": r.last_price,
            "prices_through_date": r.prices_through_date,
            "updated_at": _iso_utc(r.updated_at),
        }
        for r in rows
    ]


def count_day_scan_snapshots(db: Session) -> int:
    from app.db.models import DayScanSnapshot
    return db.query(DayScanSnapshot).count()


def get_day_scan_sync_stats(db: Session) -> dict[str, Any]:
    """Aggregate price sync dates across day scan snapshots."""
    from sqlalchemy import func

    from app.db.models import DayScanSnapshot

    row = (
        db.query(
            func.max(DayScanSnapshot.prices_through_date),
            func.min(DayScanSnapshot.prices_through_date),
            func.max(DayScanSnapshot.updated_at),
            func.count(DayScanSnapshot.symbol),
        )
        .one()
    )
    max_through, min_through, last_updated, count = row
    return {
        "max_prices_through_date": max_through,
        "min_prices_through_date": min_through,
        "last_updated_at": _iso_utc(last_updated),
        "snapshot_count": int(count or 0),
    }


# ── WidgetPreferences ─────────────────────────────────────────────────────────

def get_widget_preferences(db: Session, widget_id: str) -> dict[str, Any] | None:
    """Get preferences for a specific widget."""
    from app.db.models import WidgetPreferences
    row = db.get(WidgetPreferences, widget_id)
    if row is None:
        return None
    return {
        "widget_id": row.widget_id,
        "search_term": row.search_term or "",
        "visible_columns": json.loads(row.visible_columns) if row.visible_columns else [],
        "column_filters": json.loads(row.column_filters) if row.column_filters else {},
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def upsert_widget_preferences(
    db: Session,
    widget_id: str,
    search_term: str | None = None,
    visible_columns: list[str] | None = None,
    column_filters: dict[str, Any] | None = None,
) -> None:
    """Save or update widget preferences."""
    from app.db.models import WidgetPreferences
    row = db.get(WidgetPreferences, widget_id)
    if row is None:
        row = WidgetPreferences(widget_id=widget_id)
        db.add(row)
    if search_term is not None:
        row.search_term = search_term
    if visible_columns is not None:
        row.visible_columns = json.dumps(visible_columns)
    if column_filters is not None:
        row.column_filters = json.dumps(column_filters)
    row.updated_at = datetime.now(timezone.utc)
    db.commit()


# ── ScanResultCache ───────────────────────────────────────────────────────────

def get_scan_result_cache(db: Session, scan_type: str) -> dict[str, Any] | None:
    from app.db.models import ScanResultCache
    from app.services.scan_helpers import slim_match_payload

    row = db.get(ScanResultCache, scan_type)
    if row is None:
        return None
    raw_matches = json.loads(row.matches_json) if row.matches_json else []
    matches = [
        slim_match_payload(m) if isinstance(m, dict) else m for m in raw_matches
    ]
    from app.services.stock_lists import filter_blacklisted_matches

    blacklist = get_blacklist_symbols(db)
    matches = filter_blacklisted_matches(matches, blacklist)
    return {
        "scan_type": row.scan_type,
        "matches": matches,
        "filter": json.loads(row.filter_json) if row.filter_json else {},
        "scanned": row.scanned,
        "total": row.total,
        "last_scanned_at": _iso_utc(row.last_scanned_at),
    }


def upsert_scan_result_cache(
    db: Session,
    scan_type: str,
    matches: list[dict[str, Any]],
    *,
    scanned: int,
    total: int,
    filter_data: dict[str, Any] | None = None,
) -> None:
    from app.db.models import ScanResultCache
    from app.services.stock_lists import filter_blacklisted_matches

    blacklist = get_blacklist_symbols(db)
    matches = filter_blacklisted_matches(matches, blacklist)
    row = db.get(ScanResultCache, scan_type)
    if row is None:
        row = ScanResultCache(scan_type=scan_type)
        db.add(row)
    row.matches_json = json.dumps(matches)
    row.filter_json = json.dumps(filter_data or {})
    row.scanned = scanned
    row.total = total
    row.last_scanned_at = datetime.now(timezone.utc)
    db.commit()


def save_scan_params(
    db: Session,
    scan_type: str,
    scan_config: dict[str, Any],
) -> None:
    """Persist scanner parameters without running a scan or wiping cached matches.

    Stores the full ``scan_config`` under ``filter_json.scan_config`` so the
    Scan Profiles page can display the saved parameters read-only.
    """
    from app.db.models import ScanResultCache

    row = db.get(ScanResultCache, scan_type)
    if row is None:
        row = ScanResultCache(scan_type=scan_type)
        row.matches_json = json.dumps([])
        row.scanned = 0
        row.total = 0
        db.add(row)

    try:
        existing = json.loads(row.filter_json) if row.filter_json else {}
        if not isinstance(existing, dict):
            existing = {}
    except (json.JSONDecodeError, TypeError):
        existing = {}

    existing["scan_config"] = scan_config
    row.filter_json = json.dumps(existing)
    db.commit()


# ── Live trading engine ───────────────────────────────────────────────────────

def _serialize_live_state(row: Any) -> dict[str, Any]:
    return {
        "enabled": bool(row.enabled),
        "mode": row.mode,
        "analysis_override": bool(getattr(row, "analysis_override", False)),
        "entries_paused": bool(getattr(row, "entries_paused", False)),
        "preview_strategy": getattr(row, "preview_strategy", None) or "smart_swing",
        "capital_per_trade": row.capital_per_trade,
        "starting_capital": getattr(row, "starting_capital", None) or 1_000_000.0,
        "strategy": row.strategy,
        "last_tick_at": _iso_utc(row.last_tick_at),
        "last_data_at": _iso_utc(row.last_data_at),
        "note": row.note,
        "updated_at": _iso_utc(row.updated_at),
    }


_prev_close_cache: dict[str, tuple[str, float]] = {}
_today_pnl_sticky: dict[str, tuple[float, float]] = {}


def _cached_prev_close(symbol: str, db: Session | None = None) -> float | None:
    """Previous NSE session close — reference for today's live % change (IST)."""
    from zoneinfo import ZoneInfo

    from app.services.fetcher import fetch_history

    IST = ZoneInfo("Asia/Kolkata")
    today_ist = datetime.now(IST).date()
    today_key = today_ist.isoformat()
    cached = _prev_close_cache.get(symbol)
    if cached and cached[0] == today_key:
        return cached[1]

    def _store(prev: float) -> float:
        _prev_close_cache[symbol] = (today_key, prev)
        return prev

    if db is not None:
        since = today_ist - timedelta(days=14)
        bars = get_daily_ohlcv_bars(db, symbol, since_date=since)
        # DB stores completed sessions only — last bar before today is yesterday's close.
        completed = [b for b in bars if b["time"] < today_key]
        if completed:
            return _store(float(completed[-1]["close"]))

    df = fetch_history(symbol, period="10d", interval="1d", min_rows=1)
    if df is None or df.empty:
        return cached[1] if cached and cached[0] == today_key else None

    def _bar_ist_date(ts) -> date:
        try:
            if getattr(ts, "tzinfo", None) is not None:
                return ts.tz_convert(IST).date()
        except (TypeError, ValueError, AttributeError):
            pass
        try:
            return ts.date()
        except AttributeError:
            return today_ist

    last_bar_date = _bar_ist_date(df.index[-1])
    if last_bar_date >= today_ist and len(df) >= 2:
        # Intraday partial daily candle present — prior row is previous close.
        prev = float(df.iloc[-2]["close"])
    elif last_bar_date < today_ist:
        # Last stored daily bar is the previous session close.
        prev = float(df.iloc[-1]["close"])
    else:
        return cached[1] if cached and cached[0] == today_key else None

    return _store(prev)


def _ist_date(dt: datetime | None) -> date | None:
    if dt is None:
        return None
    from zoneinfo import ZoneInfo

    IST = ZoneInfo("Asia/Kolkata")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST).date()


def get_portfolio_summary(db: Session, strategy_key: str | None = None) -> dict[str, Any]:
    """Cash and equity for one strategy wallet (default: preview strategy)."""
    from zoneinfo import ZoneInfo

    from app.db.models import LiveTrade, LiveTradingState

    if strategy_key is None:
        strategy_key = get_preview_strategy_key(db)

    portfolio_row = get_strategy_portfolio(db, strategy_key)
    starting = float(portfolio_row.starting_capital if portfolio_row else 1_000_000.0)
    max_per_trade = float(
        portfolio_row.capital_per_trade if portfolio_row else 100_000.0
    )

    IST = ZoneInfo("Asia/Kolkata")
    today_ist = datetime.now(IST).date()

    open_rows = (
        db.query(LiveTrade)
        .filter(LiveTrade.status == "open", LiveTrade.strategy == strategy_key)
        .all()
    )
    closed_rows = (
        db.query(LiveTrade)
        .filter(LiveTrade.status == "closed", LiveTrade.strategy == strategy_key)
        .all()
    )

    realized_pnl = sum(float(t.pnl_abs or 0) for t in closed_rows)
    deployed = 0.0
    unrealized = 0.0
    holdings_current = 0.0
    for t in open_rows:
        entry = float(t.entry_price)
        qty, notional = normalize_trade_position(float(t.qty), entry)
        lp = float(t.last_price or entry)
        deployed += notional
        unrealized += qty * (lp - entry)
        holdings_current += qty * lp

    today_realized = sum(
        float(t.pnl_abs or 0)
        for t in closed_rows
        if _ist_date(t.exit_time) == today_ist
    )
    today_open_change = 0.0
    today_value_base = 0.0
    for t in open_rows:
        qty = float(t.qty)
        lp = float(t.last_price or t.entry_price)
        entry = float(t.entry_price)
        entry_day = _ist_date(t.entry_time)
        if entry_day == today_ist:
            today_open_change += qty * (lp - entry)
            today_value_base += qty * entry
        else:
            prev = _cached_prev_close(t.symbol, db)
            if prev is not None:
                today_open_change += qty * (lp - prev)
                today_value_base += qty * prev

    today_pnl = today_realized + today_open_change
    # Same base as total_pnl_pct (starting capital) so the two percentages are
    # comparable — dividing by deployed value made today's % look inflated.
    today_pnl_pct = (today_pnl / starting * 100) if starting > 0 else 0.0
    today_key = today_ist.isoformat()
    if today_value_base > 0:
        _today_pnl_sticky[today_key] = (today_pnl, today_pnl_pct)
    elif today_key in _today_pnl_sticky:
        today_pnl, today_pnl_pct = _today_pnl_sticky[today_key]

    available = max(0.0, starting + realized_pnl - deployed)
    equity = starting + realized_pnl + unrealized
    total_pnl = realized_pnl + unrealized
    trade_budget = min(max_per_trade, available)

    return {
        "starting_capital": round(starting, 2),
        "realized_pnl": round(realized_pnl, 2),
        "unrealized_pnl": round(unrealized, 2),
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round((total_pnl / starting * 100) if starting > 0 else 0.0, 2),
        "portfolio_equity": round(equity, 2),
        "deployed": round(deployed, 2),
        "holdings_invested": round(deployed, 2),
        "holdings_current": round(holdings_current, 2),
        "holdings_pnl": round(unrealized, 2),
        "holdings_pnl_pct": round((unrealized / deployed * 100) if deployed > 0 else 0.0, 2),
        "today_pnl": round(today_pnl, 2),
        "today_pnl_pct": round(today_pnl_pct, 2),
        "available_cash": round(available, 2),
        "max_per_trade": round(max_per_trade, 2),
        "trade_budget": round(trade_budget, 2),
        "open_positions": len(open_rows),
        "max_positions": int(starting // max_per_trade) if max_per_trade else 10,
        "strategy_key": strategy_key,
    }


def get_strategy_portfolio(db: Session, strategy_key: str):
    from app.db.models import LiveStrategyPortfolio

    return db.get(LiveStrategyPortfolio, strategy_key)


def list_strategy_portfolios(db: Session) -> list[Any]:
    from app.db.models import LiveStrategyPortfolio

    return db.query(LiveStrategyPortfolio).order_by(LiveStrategyPortfolio.strategy_key).all()


def get_preview_strategy_key(db: Session) -> str:
    from app.db.models import LiveStrategyPortfolio, LiveTradingState

    preview = (
        db.query(LiveStrategyPortfolio)
        .filter(LiveStrategyPortfolio.is_preview.is_(True))
        .first()
    )
    if preview:
        return preview.strategy_key
    row = db.get(LiveTradingState, 1)
    if row and getattr(row, "preview_strategy", None):
        return row.preview_strategy
    return "smart_swing"


def set_preview_strategy(db: Session, strategy_key: str) -> str:
    from app.db.models import LiveStrategyPortfolio, LiveTradingState

    row = db.get(LiveStrategyPortfolio, strategy_key)
    if row is None:
        raise ValueError(f"Unknown strategy: {strategy_key}")
    for p in db.query(LiveStrategyPortfolio).all():
        p.is_preview = p.strategy_key == strategy_key
    state = db.get(LiveTradingState, 1)
    if state is None:
        state = LiveTradingState(id=1)
        db.add(state)
    state.preview_strategy = strategy_key
    db.commit()
    return strategy_key


def get_live_trading_state(db: Session) -> dict[str, Any]:
    """Return the singleton engine state, creating it on first access."""
    from app.db.models import LiveTradingState

    row = db.get(LiveTradingState, 1)
    if row is None:
        row = LiveTradingState(id=1)
        db.add(row)
        db.commit()
    return _serialize_live_state(row)


def get_full_live_trading_state(db: Session, **extras: Any) -> dict[str, Any]:
    """Engine state merged with preview strategy portfolio summary."""
    state = get_live_trading_state(db)
    preview = extras.pop("strategy_key", None) or get_preview_strategy_key(db)
    state.update(get_portfolio_summary(db, preview))
    state["preview_strategy"] = preview
    state.update(extras)
    return state


def update_live_trading_state(db: Session, **fields: Any) -> dict[str, Any]:
    from app.db.models import LiveTradingState

    row = db.get(LiveTradingState, 1)
    if row is None:
        row = LiveTradingState(id=1)
        db.add(row)
    for key, value in fields.items():
        if hasattr(row, key):
            setattr(row, key, value)
    db.commit()
    return _serialize_live_state(row)


def _serialize_candidate(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "symbol": row.symbol,
        "source": row.source,
        "company_name": row.company_name,
        "resistance": row.resistance,
        "last_price": row.last_price,
        "target_price": row.target_price,
        "stop_price": row.stop_price,
        "volume_ratio": row.volume_ratio,
        "volume_confirmed": bool(row.volume_confirmed),
        "rationale": row.rationale,
        "status": row.status,
        "notified": bool(row.notified),
        "added_at": _iso_utc(row.added_at),
        "updated_at": _iso_utc(row.updated_at),
    }


def get_live_candidate(db: Session, symbol: str, source: str) -> Any:
    from app.db.models import LiveTradeCandidate

    return (
        db.query(LiveTradeCandidate)
        .filter(LiveTradeCandidate.symbol == symbol, LiveTradeCandidate.source == source)
        .one_or_none()
    )


def upsert_live_candidate(db: Session, symbol: str, source: str, **fields: Any) -> tuple[Any, bool]:
    """Insert or update a candidate. Returns (row, created)."""
    from sqlalchemy.exc import IntegrityError

    from app.db.models import LiveTradeCandidate

    row = get_live_candidate(db, symbol, source)
    created = row is None
    if row is None:
        row = LiveTradeCandidate(symbol=symbol, source=source)
        db.add(row)
    for key, value in fields.items():
        if hasattr(row, key):
            setattr(row, key, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        row = get_live_candidate(db, symbol, source)
        created = False
        if row is None:
            raise
        for key, value in fields.items():
            if hasattr(row, key):
                setattr(row, key, value)
        db.commit()
    db.refresh(row)
    return row, created


def list_live_candidates(db: Session) -> list[dict[str, Any]]:
    from app.db.models import LiveTradeCandidate

    rows = (
        db.query(LiveTradeCandidate)
        .order_by(LiveTradeCandidate.updated_at.desc())
        .all()
    )
    return [_serialize_candidate(r) for r in rows]


def delete_live_candidate(db: Session, symbol: str, source: str) -> bool:
    """Remove a candidate. Returns True if a row was deleted."""
    from app.db.models import LiveTradeCandidate

    row = get_live_candidate(db, symbol, source)
    if row is None:
        return False
    if row.status in ("in_trade",):
        return False
    db.delete(row)
    db.commit()
    return True


def normalize_trade_position(qty: float, entry_price: float) -> tuple[int, float]:
    """Whole NSE shares; invested amount is always qty × entry."""
    if entry_price <= 0 or qty <= 0:
        return 0, 0.0
    whole = int(qty)
    return whole, round(whole * entry_price, 2)


def _serialize_trade(row: Any) -> dict[str, Any]:
    entry = float(row.entry_price or 0)
    qty, notional = normalize_trade_position(float(row.qty or 0), entry)
    pnl_abs = row.pnl_abs
    pnl_pct = row.pnl_pct
    if qty > 0 and entry > 0:
        if row.status == "open":
            lp = float(row.last_price or entry)
            pnl_abs = round(qty * (lp - entry), 2)
            pnl_pct = round((lp - entry) / entry * 100, 2)
        elif row.status == "closed" and row.exit_price is not None:
            exit_p = float(row.exit_price)
            pnl_abs = round(qty * (exit_p - entry), 2)
            pnl_pct = round((exit_p - entry) / entry * 100, 2)

    return {
        "id": row.id,
        "symbol": row.symbol,
        "source": row.source,
        "company_name": row.company_name,
        "strategy": row.strategy,
        "entry_signal_id": getattr(row, "entry_signal_id", None),
        "entry_price": row.entry_price,
        "entry_time": _iso_utc(row.entry_time),
        "candidate_added_at": _iso_utc(getattr(row, "candidate_added_at", None)),
        "resistance": row.resistance,
        "target_price": row.target_price,
        "stop_price": row.stop_price,
        "qty": qty,
        "notional": notional,
        "peak_price": row.peak_price,
        "trough_price": getattr(row, "trough_price", None),
        "last_price": row.last_price,
        "status": row.status,
        "exit_price": row.exit_price,
        "exit_time": _iso_utc(row.exit_time),
        "exit_reason": row.exit_reason,
        "pnl_abs": row.pnl_abs,
        "pnl_pct": row.pnl_pct,
        "days_held": row.days_held,
        "rationale": row.rationale,
        "created_at": _iso_utc(row.created_at),
        "updated_at": _iso_utc(row.updated_at),
    }


def has_open_live_trade(db: Session, symbol: str, strategy: str | None = None) -> bool:
    from app.db.models import LiveTrade

    q = db.query(LiveTrade.id).filter(
        LiveTrade.symbol == symbol,
        LiveTrade.status == "open",
    )
    if strategy is not None:
        q = q.filter(LiveTrade.strategy == strategy)
    return q.first() is not None


def has_open_live_trade_for_symbol(db: Session, symbol: str) -> bool:
    """True if any strategy has an open leg on this symbol."""
    return has_open_live_trade(db, symbol, strategy=None)


def get_open_live_trade(db: Session, symbol: str) -> Any:
    from app.db.models import LiveTrade

    return (
        db.query(LiveTrade)
        .filter(LiveTrade.symbol == symbol, LiveTrade.status == "open")
        .order_by(LiveTrade.entry_time.desc())
        .first()
    )


def create_live_trade(db: Session, **fields: Any) -> Any:
    from app.db.models import LiveTrade

    row = LiveTrade(**fields)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_open_live_trades(db: Session, strategy: str | None = None) -> list[Any]:
    from app.db.models import LiveTrade

    q = db.query(LiveTrade).filter(LiveTrade.status == "open")
    if strategy is not None:
        q = q.filter(LiveTrade.strategy == strategy)
    return q.all()


def list_live_trades(
    db: Session,
    status: str = "all",
    strategy: str | None = None,
) -> list[dict[str, Any]]:
    from app.db.models import LiveTrade

    q = db.query(LiveTrade)
    if status in ("open", "closed"):
        q = q.filter(LiveTrade.status == status)
    if strategy is not None:
        q = q.filter(LiveTrade.strategy == strategy)
    rows = q.order_by(LiveTrade.entry_time.desc()).all()
    return [_serialize_trade(r) for r in rows]


def list_closed_live_trades(db: Session) -> list[dict[str, Any]]:
    return list_live_trades(db, status="closed")


# ── ScanSchedule & ScanHistory ────────────────────────────────────────────────

def get_scan_schedules(db: Session) -> list[dict[str, Any]]:
    """Get all scan schedules."""
    from app.db.models import ScanSchedule

    rows = db.query(ScanSchedule).order_by(ScanSchedule.scan_type).all()
    return [
        {
            "id": r.id,
            "scan_type": r.scan_type,
            "enabled": r.enabled,
            "frequency": r.frequency,
            "time_of_day": r.time_of_day,
            "timezone": r.timezone,
            "created_at": _iso_utc(r.created_at),
            "updated_at": _iso_utc(r.updated_at),
        }
        for r in rows
    ]


def get_scan_schedule(db: Session, scan_type: str) -> dict[str, Any] | None:
    """Get a specific scan schedule by scan_type."""
    from app.db.models import ScanSchedule

    row = db.query(ScanSchedule).filter(ScanSchedule.scan_type == scan_type).first()
    if row is None:
        return None
    return {
        "id": row.id,
        "scan_type": row.scan_type,
        "enabled": row.enabled,
        "frequency": row.frequency,
        "time_of_day": row.time_of_day,
        "timezone": row.timezone,
        "created_at": _iso_utc(row.created_at),
        "updated_at": _iso_utc(row.updated_at),
    }


def upsert_scan_schedule(
    db: Session,
    scan_type: str,
    enabled: bool,
    frequency: str,
    time_of_day: str,
    tz: str = "Asia/Kolkata",
) -> None:
    """Save or update a scan schedule."""
    from app.db.models import ScanSchedule

    row = db.query(ScanSchedule).filter(ScanSchedule.scan_type == scan_type).first()
    if row is None:
        row = ScanSchedule(scan_type=scan_type)
        db.add(row)
    row.enabled = enabled
    row.frequency = frequency
    row.time_of_day = time_of_day
    row.timezone = tz
    row.updated_at = datetime.now(timezone.utc)
    db.commit()


def log_scan_run(
    db: Session,
    scan_type: str,
    status: str,
    duration_sec: float | None = None,
    matched_count: int | None = None,
    total_scanned: int | None = None,
    error_message: str | None = None,
    triggered_by: str = "manual",
    details: dict[str, Any] | None = None,
) -> int:
    """Log a scan execution to history. Returns the new row id."""
    import json
    from app.db.models import ScanHistory

    row = ScanHistory(
        scan_type=scan_type,
        status=status,
        duration_sec=duration_sec,
        matched_count=matched_count,
        total_scanned=total_scanned,
        error_message=error_message,
        triggered_by=triggered_by,
        details_json=json.dumps(details) if details else None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return int(row.id)


def get_scan_history(db: Session, limit: int = 50) -> list[dict[str, Any]]:
    """Get recent scan history entries."""
    from app.db.models import ScanHistory

    rows = (
        db.query(ScanHistory)
        .order_by(ScanHistory.created_at.desc())
        .limit(limit)
        .all()
    )
    return [_scan_history_row_to_dict(r) for r in rows]


def get_scan_history_entry(db: Session, history_id: int) -> dict[str, Any] | None:
    """Get a single scan history entry with full details."""
    import json
    from app.db.models import ScanHistory

    row = db.query(ScanHistory).filter(ScanHistory.id == history_id).first()
    if row is None:
        return None
    out = _scan_history_row_to_dict(row, include_details=True)
    if row.details_json:
        try:
            out["details"] = json.loads(row.details_json)
        except json.JSONDecodeError:
            out["details"] = None
    return out


def _scan_history_row_to_dict(row, *, include_details: bool = False) -> dict[str, Any]:
    import json

    out: dict[str, Any] = {
        "id": row.id,
        "scan_type": row.scan_type,
        "status": row.status,
        "duration_sec": row.duration_sec,
        "matched_count": row.matched_count,
        "total_scanned": row.total_scanned,
        "error_message": row.error_message,
        "triggered_by": row.triggered_by,
        "created_at": _iso_utc(row.created_at),
    }
    if include_details and row.details_json:
        try:
            out["details"] = json.loads(row.details_json)
        except json.JSONDecodeError:
            out["details"] = None
    elif row.details_json:
        try:
            details = json.loads(row.details_json)
            out["skipped_count"] = details.get("skipped_count")
            out["error_count"] = details.get("error_count")
            out["matched_symbols"] = details.get("matched_symbols")
        except json.JSONDecodeError:
            pass
    return out


# ── BulkDeal ──────────────────────────────────────────────────────────────────

def upsert_bulk_deals(db: Session, deals: list[dict[str, Any]]) -> int:
    """Insert bulk deals, skipping duplicates. Returns count inserted."""
    from sqlalchemy.exc import IntegrityError
    from app.db.models import BulkDeal

    inserted = 0
    now = datetime.now(timezone.utc)
    for d in deals:
        sp = db.begin_nested()
        try:
            row = BulkDeal(
                deal_date=d["deal_date"],
                symbol=d["symbol"],
                security_name=d.get("security_name"),
                client_name=d["client_name"],
                buy_sell=d["buy_sell"],
                quantity=d["quantity"],
                trade_price=d["trade_price"],
                remarks=d.get("remarks"),
                fetched_at=now,
            )
            db.add(row)
            sp.commit()
            inserted += 1
        except IntegrityError:
            sp.rollback()
    db.commit()
    return inserted
    return inserted


def list_bulk_deals(
    db: Session,
    *,
    deal_date: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """List bulk deals, optionally filtered by date."""
    from app.db.models import BulkDeal

    q = db.query(BulkDeal)
    if deal_date:
        q = q.filter(BulkDeal.deal_date == deal_date)
    q = q.order_by(BulkDeal.deal_date.desc(), BulkDeal.symbol)
    rows = q.limit(limit).all()
    return [
        {
            "id": r.id,
            "deal_date": r.deal_date,
            "symbol": r.symbol,
            "security_name": r.security_name,
            "client_name": r.client_name,
            "buy_sell": r.buy_sell,
            "quantity": r.quantity,
            "trade_price": r.trade_price,
            "remarks": r.remarks,
            "fetched_at": _iso_utc(r.fetched_at),
        }
        for r in rows
    ]


def get_bulk_deal_dates(db: Session, limit: int = 30) -> list[str]:
    """Get distinct deal dates in descending order."""
    from sqlalchemy import distinct
    from app.db.models import BulkDeal

    rows = (
        db.query(distinct(BulkDeal.deal_date))
        .order_by(BulkDeal.deal_date.desc())
        .limit(limit)
        .all()
    )
    return [r[0] for r in rows]


# ── Price alerts ──────────────────────────────────────────────────────────────

def _serialize_price_alert(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "symbol": row.symbol,
        "company_name": row.company_name,
        "target_price": row.target_price,
        "direction": row.direction,
        "email": row.email,
        "note": row.note,
        "active": bool(row.active),
        "triggered_at": _iso_utc(row.triggered_at),
        "triggered_price": row.triggered_price,
        "created_at": _iso_utc(row.created_at),
        "updated_at": _iso_utc(row.updated_at),
    }


def list_price_alerts(db: Session, *, active_only: bool = False) -> list[dict[str, Any]]:
    from app.db.models import PriceAlert

    q = db.query(PriceAlert).order_by(PriceAlert.created_at.desc())
    if active_only:
        q = q.filter(PriceAlert.active == True)  # noqa: E712
    return [_serialize_price_alert(r) for r in q.all()]


def get_price_alert(db: Session, alert_id: int) -> dict[str, Any] | None:
    from app.db.models import PriceAlert

    row = db.get(PriceAlert, alert_id)
    return _serialize_price_alert(row) if row else None


def create_price_alert(
    db: Session,
    *,
    symbol: str,
    target_price: float,
    direction: str = "above",
    company_name: str | None = None,
    email: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    from app.db.models import PriceAlert

    row = PriceAlert(
        symbol=symbol.upper(),
        company_name=company_name,
        target_price=float(target_price),
        direction=direction if direction in ("above", "below") else "above",
        email=email,
        note=note,
        active=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize_price_alert(row)


def delete_price_alert(db: Session, alert_id: int) -> bool:
    from app.db.models import PriceAlert

    row = db.get(PriceAlert, alert_id)
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True


def mark_price_alert_triggered(
    db: Session,
    alert_id: int,
    *,
    triggered_price: float,
) -> dict[str, Any] | None:
    from app.db.models import PriceAlert

    row = db.get(PriceAlert, alert_id)
    if row is None:
        return None
    row.active = False
    row.triggered_at = datetime.now(timezone.utc)
    row.triggered_price = float(triggered_price)
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return _serialize_price_alert(row)


# ── User stock lists (favorites / blacklist) ───────────────────────────────────

LIST_TYPE_FAVORITE = "favorite"
LIST_TYPE_FISHY = "fishy"
LIST_TYPE_BLACKLIST = "blacklist"
LIST_TYPE_FOLLOWING = "following"
_VALID_LIST_TYPES = {
    LIST_TYPE_FAVORITE,
    LIST_TYPE_FISHY,
    LIST_TYPE_BLACKLIST,
    LIST_TYPE_FOLLOWING,
}


def _serialize_stock_list_entry(row) -> dict[str, Any]:
    from app.db.models import UserStockListEntry

    assert isinstance(row, UserStockListEntry)
    return {
        "symbol": row.symbol,
        "list_type": row.list_type,
        "note": row.note,
        "created_at": _iso_utc(row.created_at),
        "updated_at": _iso_utc(row.updated_at),
    }


def get_user_stock_lists(db: Session) -> dict[str, list[dict[str, Any]]]:
    from app.db.models import UserStockListEntry

    rows = (
        db.query(UserStockListEntry)
        .order_by(UserStockListEntry.symbol)
        .all()
    )
    favorites: list[dict[str, Any]] = []
    fishy: list[dict[str, Any]] = []
    blacklist: list[dict[str, Any]] = []
    following: list[dict[str, Any]] = []
    for row in rows:
        item = _serialize_stock_list_entry(row)
        if row.list_type == LIST_TYPE_FAVORITE:
            favorites.append(item)
        elif row.list_type == LIST_TYPE_FISHY:
            fishy.append(item)
        elif row.list_type == LIST_TYPE_BLACKLIST:
            blacklist.append(item)
        elif row.list_type == LIST_TYPE_FOLLOWING:
            following.append(item)
    return {
        "favorites": favorites,
        "fishy": fishy,
        "blacklist": blacklist,
        "following": following,
    }


def get_following_symbols(db: Session) -> list[str]:
    from app.db.models import UserStockListEntry

    rows = (
        db.query(UserStockListEntry.symbol)
        .filter(UserStockListEntry.list_type == LIST_TYPE_FOLLOWING)
        .order_by(UserStockListEntry.symbol)
        .all()
    )
    return [r[0] for r in rows]


def get_blacklist_symbols(db: Session) -> set[str]:
    from app.db.models import UserStockListEntry

    rows = (
        db.query(UserStockListEntry.symbol)
        .filter(UserStockListEntry.list_type == LIST_TYPE_BLACKLIST)
        .all()
    )
    return {r[0] for r in rows}


def upsert_stock_list_entry(
    db: Session,
    *,
    symbol: str,
    list_type: str,
    note: str | None = None,
) -> dict[str, Any]:
    from app.services.stock_lists import normalize_list_symbol
    from app.db.models import UserStockListEntry

    if list_type not in _VALID_LIST_TYPES:
        raise ValueError(f"Invalid list_type: {list_type}")

    sym = normalize_list_symbol(symbol)
    if not sym:
        raise ValueError("Symbol is required")

    # Blacklist wins — remove from favorites when blacklisting
    if list_type == LIST_TYPE_BLACKLIST:
        db.query(UserStockListEntry).filter(
            UserStockListEntry.symbol == sym,
            UserStockListEntry.list_type == LIST_TYPE_FAVORITE,
        ).delete(synchronize_session=False)

    row = (
        db.query(UserStockListEntry)
        .filter(
            UserStockListEntry.symbol == sym,
            UserStockListEntry.list_type == list_type,
        )
        .first()
    )
    if row is None:
        row = UserStockListEntry(symbol=sym, list_type=list_type, note=note)
        db.add(row)
    else:
        row.note = note
        row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return _serialize_stock_list_entry(row)


def remove_stock_list_entry(db: Session, *, symbol: str, list_type: str) -> bool:
    from app.services.stock_lists import normalize_list_symbol
    from app.db.models import UserStockListEntry

    sym = normalize_list_symbol(symbol)
    deleted = (
        db.query(UserStockListEntry)
        .filter(
            UserStockListEntry.symbol == sym,
            UserStockListEntry.list_type == list_type,
        )
        .delete(synchronize_session=False)
    )
    db.commit()
    return deleted > 0


def replace_user_stock_lists(
    db: Session,
    *,
    favorites: list[str],
    blacklist: list[str],
    notes: dict[str, str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Replace entire favorite/blacklist sets (manual widget save)."""
    from app.services.stock_lists import normalize_list_symbol
    from app.db.models import UserStockListEntry

    notes = notes or {}
    fav_syms = []
    seen: set[str] = set()
    for raw in favorites:
        sym = normalize_list_symbol(str(raw).strip())
        if sym and sym not in seen:
            fav_syms.append(sym)
            seen.add(sym)

    bl_syms: list[str] = []
    bl_seen: set[str] = set()
    for raw in blacklist:
        sym = normalize_list_symbol(str(raw).strip())
        if sym and sym not in bl_seen:
            bl_syms.append(sym)
            bl_seen.add(sym)

    fav_set = set(fav_syms) - set(bl_syms)

    # Only replace favorite/blacklist sets; preserve independent "fishy" flags.
    db.query(UserStockListEntry).filter(
        UserStockListEntry.list_type.in_([LIST_TYPE_FAVORITE, LIST_TYPE_BLACKLIST])
    ).delete(synchronize_session=False)
    db.flush()

    for sym in sorted(fav_set):
        db.add(
            UserStockListEntry(
                symbol=sym,
                list_type=LIST_TYPE_FAVORITE,
                note=notes.get(sym) or notes.get(raw) or None,
            )
        )
    for sym in sorted(bl_syms):
        db.add(
            UserStockListEntry(
                symbol=sym,
                list_type=LIST_TYPE_BLACKLIST,
                note=notes.get(sym) or None,
            )
        )
    db.commit()
    return get_user_stock_lists(db)


# ── IpoIntel (scraped GMP + subscription) ─────────────────────────────────────

_IPO_INTEL_FIELDS = (
    "display_name", "ipo_type", "status", "price_band", "ipo_size", "lot_size",
    "gmp", "gmp_pct", "rating", "open_date", "close_date", "listing_date",
    "sub_qib", "sub_nii", "sub_retail", "sub_total", "sub_applications",
    "sub_as_of", "gmp_updated_at", "sources", "fetched_at",
    "upstox_verified", "upstox_symbol", "isin", "industry", "upstox_id",
)


def upsert_ipo_intel(db: Session, *, name_key: str, **fields: Any):
    from app.db.models import IpoIntel

    row = db.query(IpoIntel).filter(IpoIntel.name_key == name_key).first()
    if row is None:
        row = IpoIntel(name_key=name_key, display_name=fields.get("display_name") or name_key)
        db.add(row)
    for field in _IPO_INTEL_FIELDS:
        if field in fields and fields[field] is not None:
            setattr(row, field, fields[field])
    db.commit()
    return row


def list_ipo_intel(db: Session) -> list[dict[str, Any]]:
    from app.db.models import IpoIntel

    rows = db.query(IpoIntel).order_by(IpoIntel.fetched_at.desc(), IpoIntel.display_name).all()
    return [
        {
            "name_key": r.name_key,
            "display_name": r.display_name,
            "ipo_type": r.ipo_type,
            "status": r.status,
            "price_band": r.price_band,
            "ipo_size": r.ipo_size,
            "lot_size": r.lot_size,
            "gmp": r.gmp,
            "gmp_pct": r.gmp_pct,
            "rating": r.rating,
            "open_date": r.open_date,
            "close_date": r.close_date,
            "listing_date": r.listing_date,
            "sub_qib": r.sub_qib,
            "sub_nii": r.sub_nii,
            "sub_retail": r.sub_retail,
            "sub_total": r.sub_total,
            "sub_applications": r.sub_applications,
            "sub_as_of": r.sub_as_of,
            "gmp_updated_at": r.gmp_updated_at,
            "sources": r.sources,
            "upstox_verified": bool(r.upstox_verified),
            "upstox_symbol": r.upstox_symbol,
            "isin": r.isin,
            "industry": r.industry,
            "upstox_id": r.upstox_id,
            "fetched_at": _iso_utc(r.fetched_at),
        }
        for r in rows
    ]


def prune_ipo_intel(db: Session, *, older_than: datetime) -> int:
    """Delete rows whose data hasn't been refreshed since `older_than`."""
    from app.db.models import IpoIntel

    deleted = (
        db.query(IpoIntel).filter(IpoIntel.fetched_at < older_than).delete()
    )
    db.commit()
    return int(deleted)

