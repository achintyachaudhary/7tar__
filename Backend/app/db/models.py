"""SQLAlchemy ORM table definitions."""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class StockProfile(Base):
    """Cached company profile: sector, industry, market cap, overall score."""

    __tablename__ = "stock_profiles"

    symbol: Mapped[str] = mapped_column(String, primary_key=True)
    company_name: Mapped[str | None] = mapped_column(String, nullable=True)
    sector: Mapped[str | None] = mapped_column(String, nullable=True)
    industry: Mapped[str | None] = mapped_column(String, nullable=True)
    market_cap_cr: Mapped[float | None] = mapped_column(Float, nullable=True)
    cap_category: Mapped[str | None] = mapped_column(String, nullable=True)
    overall_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class HoldingsCache(Base):
    """Latest (most recent period) shareholding snapshot per symbol."""

    __tablename__ = "holdings_cache"

    symbol: Mapped[str] = mapped_column(String, primary_key=True)
    promoter_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    fii_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    dii_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    public_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    retail_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    as_of: Mapped[str | None] = mapped_column(String, nullable=True)
    last_fetched: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )
    # Full historical JSON stored as text for the modal chart
    history_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class FinancialCache(Base):
    """One row per (symbol, period_label, is_quarterly) financial data point."""

    __tablename__ = "financial_cache"
    __table_args__ = (
        Index("ix_financial_symbol_quarterly_period", "symbol", "is_quarterly", "period_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    period_label: Mapped[str] = mapped_column(String, nullable=False)
    is_quarterly: Mapped[bool] = mapped_column(Boolean, default=True)
    revenue_cr: Mapped[float | None] = mapped_column(Float, nullable=True)
    profit_cr: Mapped[float | None] = mapped_column(Float, nullable=True)
    period_date: Mapped[str | None] = mapped_column(String, nullable=True)
    last_fetched: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now
    )


class UserPreferences(Base):
    """Generic key-value store for user settings (theme, etc.)."""

    __tablename__ = "user_preferences"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)


class DashboardWidget(Base):
    """One row per widget in the user's dashboard layout."""

    __tablename__ = "dashboard_widgets"
    __table_args__ = (Index("ix_dashboard_widgets_position", "position"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    widget_type: Mapped[str] = mapped_column(String, nullable=False)
    size: Mapped[str] = mapped_column(String, default="md")  # sm | md | lg
    position: Mapped[int] = mapped_column(Integer, default=0)
    config_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class MarketIndexCache(Base):
    """Cached quote + 1Y daily bars for NIFTY / BANKNIFTY / SENSEX."""

    __tablename__ = "market_index_cache"

    index_id: Mapped[str] = mapped_column(String, primary_key=True)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    yf_symbol: Mapped[str] = mapped_column(String, nullable=False)
    last_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    change_abs: Mapped[float | None] = mapped_column(Float, nullable=True)
    change_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    bars_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    quote_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    bars_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class IpoListing(Base):
    """
    Shared IPO catalog for IPO Tracker + IPO Research (single source of truth).
    """

    __tablename__ = "ipo_listings"
    __table_args__ = (
        Index("ix_ipo_listing_date", "listing_date"),
        Index("ix_ipo_ml_status_listing_date", "ml_status", "listing_date"),
        Index("ix_ipo_updated_at", "updated_at"),
    )

    symbol: Mapped[str] = mapped_column(String, primary_key=True)
    company_name: Mapped[str | None] = mapped_column(String, nullable=True)
    security_type: Mapped[str] = mapped_column(String, default="")
    ipo_start_date: Mapped[str] = mapped_column(String, default="")
    ipo_end_date: Mapped[str] = mapped_column(String, default="")
    listing_date: Mapped[str] = mapped_column(String, nullable=False)
    listing_date_display: Mapped[str] = mapped_column(String, default="")
    issue_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_range: Mapped[str] = mapped_column(String, default="")

    yf_symbol: Mapped[str | None] = mapped_column(String, nullable=True)
    listing_open: Mapped[float | None] = mapped_column(Float, nullable=True)
    listing_close: Mapped[float | None] = mapped_column(Float, nullable=True)
    listing_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    listing_day_gain_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    gain_vs_issue_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    gain_vs_listing_close_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    gain_listing_open_to_current_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    market_status: Mapped[str] = mapped_column(
        String, default="pending"
    )  # pending | listed | no_market_data

    features_json: Mapped[str] = mapped_column(Text, default="{}")
    targets_json: Mapped[str] = mapped_column(Text, default="{}")
    ml_status: Mapped[str] = mapped_column(
        String, default="pending"
    )  # pending | ready | no_market_data | incomplete

    price_fetched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ml_built_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class IpoMlFeatureRow(Base):
    """Deprecated: migrated to ipo_listings. Kept for DB migration only."""

    __tablename__ = "ipo_ml_features"

    symbol: Mapped[str] = mapped_column(String, primary_key=True)
    listing_date: Mapped[str] = mapped_column(String, nullable=False)
    company_name: Mapped[str | None] = mapped_column(String, nullable=True)
    features_json: Mapped[str] = mapped_column(Text, nullable=False)
    targets_json: Mapped[str] = mapped_column(Text, nullable=False)
    enrichment_status: Mapped[str] = mapped_column(String, default="ready")
    built_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class IpoResearchRun(Base):
    """One ML experiment execution (scikit-learn) with stored outcomes."""

    __tablename__ = "ipo_research_runs"
    __table_args__ = (Index("ix_ipo_research_created_at", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    algorithm: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default="running")  # running | completed | failed
    params_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    metrics_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    insights_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    sample_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class IpoLlmResearch(Base):
    """IPO subscription / issue details from LLM (Gemini, etc.)."""

    __tablename__ = "ipo_llm_research"

    symbol: Mapped[str] = mapped_column(String, primary_key=True)
    provider: Mapped[str] = mapped_column(String, default="gemini")
    status: Mapped[str] = mapped_column(String, default="fetched")  # fetched | failed
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class StockUniverse(Base):
    """Exhaustive list of all NSE stocks available for scanning."""

    __tablename__ = "stock_universe"
    __table_args__ = (
        Index("ix_stock_universe_active_listing", "is_active", "data_from_listing"),
    )

    symbol: Mapped[str] = mapped_column(String, primary_key=True)
    company_name: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now
    )
    last_scanned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    listing_date: Mapped[str | None] = mapped_column(String, nullable=True)
    data_from_listing: Mapped[bool] = mapped_column(Boolean, default=False)


class StockPriceDaily(Base):
    """Daily OHLCV time series per symbol."""

    __tablename__ = "stock_prices_daily"
    __table_args__ = (
        UniqueConstraint("symbol", "trade_date", name="uq_symbol_trade_date"),
        # uq_symbol_trade_date backs symbol lookups and trade_date ordering per symbol.
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    trade_date: Mapped[str] = mapped_column(String, nullable=False)
    open: Mapped[float | None] = mapped_column(Float, nullable=True)
    high: Mapped[float | None] = mapped_column(Float, nullable=True)
    low: Mapped[float | None] = mapped_column(Float, nullable=True)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now
    )


class DayScanSnapshot(Base):
    """Latest computed day-scan metrics per symbol for dashboard table."""

    __tablename__ = "day_scan_snapshots"
    __table_args__ = (Index("ix_day_scan_market_cap_cr", "market_cap_cr"),)

    symbol: Mapped[str] = mapped_column(String, primary_key=True)
    company_name: Mapped[str | None] = mapped_column(String, nullable=True)
    industry: Mapped[str | None] = mapped_column(String, nullable=True)
    market_cap_cr: Mapped[float | None] = mapped_column(Float, nullable=True)
    pe_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    roce_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    return_1d_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    return_1w_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    return_1m_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    return_1y_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    prices_through_date: Mapped[str | None] = mapped_column(String, nullable=True)
    fundamentals_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class WidgetPreferences(Base):
    """User preferences for widget display: search, visible columns, etc."""

    __tablename__ = "widget_preferences"

    widget_id: Mapped[str] = mapped_column(String, primary_key=True)
    search_term: Mapped[str | None] = mapped_column(String, nullable=True)
    visible_columns: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array
    column_filters: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON object
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class ScanResultCache(Base):
    """Persisted latest scan results for BrSt / Multi Year (until user refreshes)."""

    __tablename__ = "scan_result_cache"

    scan_type: Mapped[str] = mapped_column(String, primary_key=True)  # brst | multi_year
    matches_json: Mapped[str] = mapped_column(Text, default="[]")
    filter_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    scanned: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    last_scanned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class LiveTradingState(Base):
    """Singleton row holding the live paper-trading engine state."""

    __tablename__ = "live_trading_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # off | market_off | analysis | live
    mode: Mapped[str] = mapped_column(String, default="market_off")
    # User requested analysis while market is closed (cleared automatically when market opens).
    analysis_override: Mapped[bool] = mapped_column(Boolean, default=False)
    # Kill switch: block new entries; open trades still managed (stops, targets, manual exit).
    entries_paused: Mapped[bool] = mapped_column(Boolean, default=False)
    capital_per_trade: Mapped[float] = mapped_column(Float, default=100000.0)
    starting_capital: Mapped[float] = mapped_column(Float, default=1000000.0)
    strategy: Mapped[str] = mapped_column(String, default="smart_swing")
    last_tick_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_data_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    note: Mapped[str | None] = mapped_column(String, nullable=True)
    # Persisted sync config: which screeners and exclusions the engine should respect
    sync_screeners_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    sync_excluded_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    preview_strategy: Mapped[str] = mapped_column(String, default="smart_swing")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class LiveStrategyPortfolio(Base):
    """Independent paper wallet per exit strategy (₹10L each)."""

    __tablename__ = "live_strategy_portfolios"

    strategy_key: Mapped[str] = mapped_column(String, primary_key=True)
    label: Mapped[str] = mapped_column(String, nullable=False)
    starting_capital: Mapped[float] = mapped_column(Float, default=1_000_000.0)
    capital_per_trade: Mapped[float] = mapped_column(Float, default=100_000.0)
    is_preview: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class LiveTradeCandidate(Base):
    """A breakout candidate the engine is watching for a potential entry."""

    __tablename__ = "live_trade_candidates"
    __table_args__ = (
        UniqueConstraint("symbol", "source", name="uq_candidate_symbol_source"),
        Index("ix_live_candidates_updated_at", "updated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)  # brst | multi_year
    company_name: Mapped[str | None] = mapped_column(String, nullable=True)
    resistance: Mapped[float] = mapped_column(Float, nullable=False)
    last_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    # watching | armed | in_trade | closed | skipped
    status: Mapped[str] = mapped_column(String, default="watching")
    notified: Mapped[bool] = mapped_column(Boolean, default=False)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class LiveTrade(Base):
    """A paper swing trade opened by the live-trading engine."""

    __tablename__ = "live_trades"
    __table_args__ = (
        Index("ix_live_trades_status_entry_time", "status", "entry_time"),
        Index("ix_live_trades_symbol_status", "symbol", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)  # brst | multi_year
    company_name: Mapped[str | None] = mapped_column(String, nullable=True)
    strategy: Mapped[str] = mapped_column(String, default="smart_swing")
    entry_signal_id: Mapped[str | None] = mapped_column(String, nullable=True)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    entry_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    candidate_added_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resistance: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    qty: Mapped[float] = mapped_column(Float, default=0.0)
    notional: Mapped[float] = mapped_column(Float, default=0.0)
    peak_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    trough_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String, default="open")  # open | closed
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    exit_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    pnl_abs: Mapped[float | None] = mapped_column(Float, nullable=True)
    pnl_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    days_held: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class BulkDeal(Base):
    """NSE bulk deal record fetched daily."""

    __tablename__ = "bulk_deals"
    __table_args__ = (
        UniqueConstraint("deal_date", "symbol", "client_name", "buy_sell", name="uq_bulk_deal"),
        Index("ix_bulk_deals_deal_date_symbol", "deal_date", "symbol"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    deal_date: Mapped[str] = mapped_column(String, nullable=False)
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    security_name: Mapped[str | None] = mapped_column(String, nullable=True)
    client_name: Mapped[str] = mapped_column(String, nullable=False)
    buy_sell: Mapped[str] = mapped_column(String(4), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    trade_price: Mapped[float] = mapped_column(Float, nullable=False)
    remarks: Mapped[str | None] = mapped_column(String, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ScanSchedule(Base):
    """Scheduled scan configuration for automated background execution."""

    __tablename__ = "scan_schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_type: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    frequency: Mapped[str] = mapped_column(String(20), nullable=False)  # daily | weekly
    time_of_day: Mapped[str] = mapped_column(String, nullable=False)  # HH:MM format
    timezone: Mapped[str] = mapped_column(String, default="Asia/Kolkata")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class ScanHistory(Base):
    """Log of scan executions (scheduled or manual) for history display."""

    __tablename__ = "scan_history"
    __table_args__ = (
        Index("ix_scan_history_scan_type_created", "scan_type", "created_at"),
        Index("ix_scan_history_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String, default="completed")  # completed | failed
    duration_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    matched_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_scanned: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    triggered_by: Mapped[str] = mapped_column(String, default="manual")  # manual | scheduled
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class SectorRotationCache(Base):
    """Cached sector rotation analysis results (computed daily)."""

    __tablename__ = "sector_rotation_cache"
    __table_args__ = (Index("ix_sector_rotation_computed_at", "computed_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    data_json: Mapped[str] = mapped_column(Text, nullable=False)


class PriceAlert(Base):
    """User price alert — triggers email + browser notification when hit."""

    __tablename__ = "price_alerts"
    __table_args__ = (
        Index("ix_price_alerts_active_symbol", "active", "symbol"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    company_name: Mapped[str | None] = mapped_column(String, nullable=True)
    target_price: Mapped[float] = mapped_column(Float, nullable=False)
    # above | below
    direction: Mapped[str] = mapped_column(String, default="above")
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    note: Mapped[str | None] = mapped_column(String, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    triggered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    triggered_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class UserStockListEntry(Base):
    """User-curated favorite and blacklisted symbols (persisted across sessions)."""

    __tablename__ = "user_stock_lists"
    __table_args__ = (
        UniqueConstraint("symbol", "list_type", name="uq_user_stock_lists_symbol_type"),
        Index("ix_user_stock_lists_type", "list_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    list_type: Mapped[str] = mapped_column(String, nullable=False)  # favorite | fishy | blacklist
    note: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class IpoIntel(Base):
    """Latest scraped IPO market intel — GMP, subscription, dates (one row per IPO).

    Scraped from public IPO trackers via headless Chromium; refreshed manually
    or on the ipo_intel schedule. Rows are upserted by normalized name and
    pruned once they go stale.
    """

    __tablename__ = "ipo_intel"
    __table_args__ = (Index("ix_ipo_intel_status", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Normalized join key, e.g. "horizon reclaim india"
    name_key: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    ipo_type: Mapped[str | None] = mapped_column(String, nullable=True)  # mainboard | sme
    status: Mapped[str | None] = mapped_column(String, nullable=True)  # upcoming|open|closed|listed
    price_band: Mapped[str | None] = mapped_column(String, nullable=True)
    ipo_size: Mapped[str | None] = mapped_column(String, nullable=True)
    lot_size: Mapped[str | None] = mapped_column(String, nullable=True)
    gmp: Mapped[float | None] = mapped_column(Float, nullable=True)
    gmp_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)  # fire rating 0–5
    open_date: Mapped[str | None] = mapped_column(String, nullable=True)
    close_date: Mapped[str | None] = mapped_column(String, nullable=True)
    listing_date: Mapped[str | None] = mapped_column(String, nullable=True)
    sub_qib: Mapped[float | None] = mapped_column(Float, nullable=True)
    sub_nii: Mapped[float | None] = mapped_column(Float, nullable=True)
    sub_retail: Mapped[float | None] = mapped_column(Float, nullable=True)
    sub_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    sub_applications: Mapped[str | None] = mapped_column(String, nullable=True)
    sub_as_of: Mapped[str | None] = mapped_column(String, nullable=True)
    gmp_updated_at: Mapped[str | None] = mapped_column(String, nullable=True)
    sources: Mapped[str | None] = mapped_column(String, nullable=True)
    # Upstox verification (authoritative catalog match)
    upstox_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    upstox_symbol: Mapped[str | None] = mapped_column(String, nullable=True)
    isin: Mapped[str | None] = mapped_column(String, nullable=True)
    industry: Mapped[str | None] = mapped_column(String, nullable=True)
    upstox_id: Mapped[str | None] = mapped_column(String, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

