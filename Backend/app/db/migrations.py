"""Lightweight schema migrations (add columns without Alembic)."""

import json
import logging
from pathlib import Path
from sqlalchemy import inspect, text

from app.db.database import engine, SessionLocal, is_postgres, is_sqlite
from app.db import crud

logger = logging.getLogger(__name__)


def _bool_default_false() -> str:
    return "false" if is_postgres() else "0"


def _now_sql() -> str:
    return "NOW()" if is_postgres() else "datetime('now')"


def migrate_ipo_llm_research() -> None:
    insp = inspect(engine)
    if "ipo_llm_research" not in insp.get_table_names():
        return

    cols = {c["name"] for c in insp.get_columns("ipo_llm_research")}
    with engine.begin() as conn:
        if "status" not in cols:
            conn.execute(
                text(
                    "ALTER TABLE ipo_llm_research "
                    "ADD COLUMN status VARCHAR NOT NULL DEFAULT 'fetched'"
                )
            )
        if "error_message" not in cols:
            conn.execute(
                text("ALTER TABLE ipo_llm_research ADD COLUMN error_message TEXT")
            )
        # Backfill legacy rows
        conn.execute(
            text(
                "UPDATE ipo_llm_research SET status = 'fetched' "
                "WHERE status IS NULL OR status = ''"
            )
        )


def migrate_ipo_ml_features() -> None:
    insp = inspect(engine)
    if "ipo_ml_features" not in insp.get_table_names():
        return

    cols = {c["name"] for c in insp.get_columns("ipo_ml_features")}
    with engine.begin() as conn:
        if "enrichment_status" not in cols:
            conn.execute(
                text(
                    "ALTER TABLE ipo_ml_features "
                    "ADD COLUMN enrichment_status VARCHAR NOT NULL DEFAULT 'ready'"
                )
            )
        conn.execute(
            text(
                "UPDATE ipo_ml_features SET enrichment_status = 'ready' "
                "WHERE enrichment_status IS NULL OR enrichment_status = ''"
            )
        )


def migrate_ipo_listings() -> None:
    """Create ipo_listings and copy legacy ipo_ml_features rows."""
    import app.db.models as _models  # noqa: F401 — register tables

    _models.IpoListing.__table__.create(bind=engine, checkfirst=True)

    insp = inspect(engine)
    if "ipo_listings" not in insp.get_table_names():
        return

    # Copy from ipo_ml_features if present
    if "ipo_ml_features" in insp.get_table_names():
        with engine.begin() as conn:
            if is_postgres():
                conn.execute(
                    text(
                        """
                        INSERT INTO ipo_listings (
                            symbol, company_name, listing_date, features_json, targets_json,
                            ml_status, ml_built_at, market_status, updated_at
                        )
                        SELECT symbol, company_name, listing_date, features_json, targets_json,
                               CASE enrichment_status
                                 WHEN 'ready' THEN 'ready'
                                 WHEN 'no_market_data' THEN 'no_market_data'
                                 ELSE 'incomplete'
                               END,
                               built_at,
                               CASE enrichment_status
                                 WHEN 'no_market_data' THEN 'no_market_data'
                                 ELSE 'listed'
                               END,
                               built_at
                        FROM ipo_ml_features
                        ON CONFLICT (symbol) DO NOTHING
                        """
                    )
                )
            else:
                conn.execute(
                    text(
                        """
                        INSERT OR IGNORE INTO ipo_listings (
                            symbol, company_name, listing_date, features_json, targets_json,
                            ml_status, ml_built_at, market_status, updated_at
                        )
                        SELECT symbol, company_name, listing_date, features_json, targets_json,
                               CASE enrichment_status
                                 WHEN 'ready' THEN 'ready'
                                 WHEN 'no_market_data' THEN 'no_market_data'
                                 ELSE 'incomplete'
                               END,
                               built_at,
                               CASE enrichment_status
                                 WHEN 'no_market_data' THEN 'no_market_data'
                                 ELSE 'listed'
                               END,
                               built_at
                        FROM ipo_ml_features
                        """
                    )
                )


def migrate_stock_universe() -> None:
    """Populate StockUniverse table from nse_all.json cache file."""
    import app.db.models as _models  # noqa: F401 — register tables

    migrate_stock_universe_columns()

    # Create table if it doesn't exist
    _models.StockUniverse.__table__.create(bind=engine, checkfirst=True)
    
    with SessionLocal() as db:
        existing_count = crud.count_stock_universe(db)
        
        # Only populate if table is empty or has very few entries
        if existing_count > 100:
            logger.info("StockUniverse already populated with %d stocks", existing_count)
            return
        
        # Find nse_all.json cache file (bundled under app/cache, runtime under data/cache)
        backend_dir = Path(__file__).resolve().parents[2]
        nse_all_path = backend_dir / "data" / "cache" / "nse_all.json"
        if not nse_all_path.exists():
            nse_all_path = backend_dir / "app" / "cache" / "nse_all.json"
        
        if not nse_all_path.exists():
            logger.warning("nse_all.json not found at %s, skipping StockUniverse population", nse_all_path)
            return
        
        try:
            with open(nse_all_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                symbols = data.get("symbols", [])
            
            if not symbols:
                logger.warning("No symbols found in nse_all.json")
                return
            
            inserted = crud.bulk_upsert_stock_universe(db, symbols)
            logger.info("StockUniverse populated: %d new stocks added (total: %d)", inserted, len(symbols))
        except Exception:
            logger.exception("Failed to populate StockUniverse from nse_all.json")
            raise


def migrate_stock_universe_columns() -> None:
    """Add listing_date and data_from_listing columns to stock_universe."""
    import app.db.models as _models  # noqa: F401

    _models.StockUniverse.__table__.create(bind=engine, checkfirst=True)

    insp = inspect(engine)
    if "stock_universe" not in insp.get_table_names():
        return

    cols = {c["name"] for c in insp.get_columns("stock_universe")}
    with engine.begin() as conn:
        if "listing_date" not in cols:
            conn.execute(text("ALTER TABLE stock_universe ADD COLUMN listing_date VARCHAR"))
        if "data_from_listing" not in cols:
            conn.execute(
                text(
                    f"ALTER TABLE stock_universe "
                    f"ADD COLUMN data_from_listing BOOLEAN NOT NULL DEFAULT {_bool_default_false()}"
                )
            )


def migrate_widget_preferences() -> None:
    """Create widget_preferences table for storing search/column filters."""
    import app.db.models as _models  # noqa: F401

    _models.WidgetPreferences.__table__.create(bind=engine, checkfirst=True)
    logger.info("WidgetPreferences table migration completed")


def migrate_scan_result_cache() -> None:
    """Create scan_result_cache table for BrSt / Multi Year persisted results."""
    import app.db.models as _models  # noqa: F401

    _models.ScanResultCache.__table__.create(bind=engine, checkfirst=True)
    logger.info("ScanResultCache table migration completed")


def migrate_live_trading() -> None:
    """Create live-trading engine tables (state, candidates, trades)."""
    import app.db.models as _models  # noqa: F401

    _models.LiveTradingState.__table__.create(bind=engine, checkfirst=True)
    _models.LiveTradeCandidate.__table__.create(bind=engine, checkfirst=True)
    _models.LiveTrade.__table__.create(bind=engine, checkfirst=True)

    insp = inspect(engine)
    if "live_trading_state" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("live_trading_state")}
        with engine.begin() as conn:
            if "analysis_override" not in cols:
                conn.execute(
                    text(
                        f"ALTER TABLE live_trading_state "
                        f"ADD COLUMN analysis_override BOOLEAN NOT NULL DEFAULT {_bool_default_false()}"
                    )
                )
            if "sync_screeners_json" not in cols:
                conn.execute(
                    text(
                        "ALTER TABLE live_trading_state "
                        "ADD COLUMN sync_screeners_json TEXT"
                    )
                )
            if "sync_excluded_json" not in cols:
                conn.execute(
                    text(
                        "ALTER TABLE live_trading_state "
                        "ADD COLUMN sync_excluded_json TEXT"
                    )
                )
            if "entries_paused" not in cols:
                conn.execute(
                    text(
                        f"ALTER TABLE live_trading_state "
                        f"ADD COLUMN entries_paused BOOLEAN NOT NULL DEFAULT {_bool_default_false()}"
                    )
                )
            if "starting_capital" not in cols:
                conn.execute(
                    text(
                        "ALTER TABLE live_trading_state "
                        "ADD COLUMN starting_capital FLOAT NOT NULL DEFAULT 1000000.0"
                    )
                )
                conn.execute(
                    text(
                        "UPDATE live_trading_state "
                        "SET starting_capital = 1000000.0, capital_per_trade = 100000.0 "
                        "WHERE id = 1"
                    )
                )
                # Fresh portfolio reset: clear trades, release candidates.
                if "live_trades" in insp.get_table_names():
                    conn.execute(text("DELETE FROM live_trades"))
                if "live_trade_candidates" in insp.get_table_names():
                    conn.execute(
                        text(
                            "UPDATE live_trade_candidates "
                            "SET status = 'watching' WHERE status = 'in_trade'"
                        )
                    )
                logger.info(
                    "Portfolio reset: 10L starting capital, all trades cleared"
                )

    if "live_trades" in insp.get_table_names():
        trade_cols = {c["name"] for c in insp.get_columns("live_trades")}
        with engine.begin() as conn:
            if "trough_price" not in trade_cols:
                conn.execute(
                    text("ALTER TABLE live_trades ADD COLUMN trough_price FLOAT")
                )
            if "candidate_added_at" not in trade_cols:
                ts_type = "TIMESTAMP WITH TIME ZONE" if is_postgres() else "DATETIME"
                conn.execute(
                    text(f"ALTER TABLE live_trades ADD COLUMN candidate_added_at {ts_type}")
                )

            now_fn = _now_sql()
            dup_symbols = conn.execute(
                text(
                    """
                    SELECT symbol FROM live_trades
                    WHERE status = 'open'
                    GROUP BY symbol
                    HAVING COUNT(*) > 1
                    """
                )
            ).fetchall()
            for (symbol,) in dup_symbols:
                rows = conn.execute(
                    text(
                        """
                        SELECT id, entry_price, last_price
                        FROM live_trades
                        WHERE status = 'open' AND symbol = :symbol
                        ORDER BY entry_time ASC, id ASC
                        """
                    ),
                    {"symbol": symbol},
                ).fetchall()
                keep_id = rows[0][0]
                for trade_id, entry_price, last_price in rows[1:]:
                    exit_price = last_price if last_price is not None else entry_price
                    pnl_pct = round((exit_price / entry_price - 1) * 100, 2) if entry_price else 0.0
                    conn.execute(
                        text(
                            f"""
                            UPDATE live_trades
                            SET status = 'closed',
                                exit_reason = 'duplicate_cleanup',
                                exit_time = {now_fn},
                                exit_price = :exit_price,
                                pnl_pct = :pnl_pct,
                                pnl_abs = qty * (:exit_price - entry_price),
                                days_held = 0
                            WHERE id = :id
                            """
                        ),
                        {
                            "id": trade_id,
                            "exit_price": exit_price,
                            "pnl_pct": pnl_pct,
                        },
                    )
                logger.info(
                    "Closed %d duplicate open trade(s) for %s (kept id=%s)",
                    len(rows) - 1,
                    symbol,
                    keep_id,
                )

            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_live_trades_one_open_per_symbol "
                    "ON live_trades(symbol) WHERE status = 'open'"
                )
            )

    _migrate_parallel_strategies(insp)

    logger.info("LiveTrading tables migration completed")


def _migrate_parallel_strategies(insp) -> None:
    """Multi-strategy portfolios, entry_signal_id, per-strategy open uniqueness."""
    import app.db.models as _models  # noqa: F401

    _models.LiveStrategyPortfolio.__table__.create(bind=engine, checkfirst=True)

    if "live_trading_state" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("live_trading_state")}
        with engine.begin() as conn:
            if "preview_strategy" not in cols:
                conn.execute(
                    text(
                        "ALTER TABLE live_trading_state "
                        "ADD COLUMN preview_strategy VARCHAR NOT NULL DEFAULT 'smart_swing'"
                    )
                )

    if "live_trades" in insp.get_table_names():
        trade_cols = {c["name"] for c in insp.get_columns("live_trades")}
        with engine.begin() as conn:
            if "entry_signal_id" not in trade_cols:
                conn.execute(
                    text("ALTER TABLE live_trades ADD COLUMN entry_signal_id VARCHAR")
                )
            conn.execute(text("DROP INDEX IF EXISTS uq_live_trades_one_open_per_symbol"))
            if is_postgres():
                conn.execute(
                    text(
                        "CREATE UNIQUE INDEX IF NOT EXISTS uq_live_trades_one_open_per_symbol_strategy "
                        "ON live_trades(symbol, strategy) WHERE status = 'open'"
                    )
                )
            else:
                conn.execute(
                    text(
                        "CREATE UNIQUE INDEX IF NOT EXISTS uq_live_trades_one_open_per_symbol_strategy "
                        "ON live_trades(symbol, strategy) WHERE status = 'open'"
                    )
                )

    # Seed strategy portfolios from live_trading.STRATEGIES
    from app.services.live_trading import STRATEGIES

    with SessionLocal() as db:
        from app.db.models import LiveStrategyPortfolio

        for strat in STRATEGIES:
            row = db.get(LiveStrategyPortfolio, strat["key"])
            if row is None:
                db.add(
                    LiveStrategyPortfolio(
                        strategy_key=strat["key"],
                        label=strat["label"].replace(" (executed)", ""),
                        starting_capital=1_000_000.0,
                        capital_per_trade=100_000.0,
                        is_preview=strat["key"] == "smart_swing",
                    )
                )
        db.commit()
        previews = db.query(LiveStrategyPortfolio).filter(LiveStrategyPortfolio.is_preview.is_(True)).count()
        if previews == 0:
            row = db.get(LiveStrategyPortfolio, "smart_swing")
            if row:
                row.is_preview = True
                db.commit()
        elif previews > 1:
            first = True
            for row in db.query(LiveStrategyPortfolio).all():
                row.is_preview = first and row.strategy_key == "smart_swing"
                first = False
            db.get(LiveStrategyPortfolio, "smart_swing").is_preview = True
            db.commit()

    logger.info("Parallel strategy portfolios migration completed")


def migrate_scan_schedules() -> None:
    """Create scan schedule and history tables for automated scan execution."""
    import app.db.models as _models  # noqa: F401

    _models.ScanSchedule.__table__.create(bind=engine, checkfirst=True)
    _models.ScanHistory.__table__.create(bind=engine, checkfirst=True)

    # Seed default schedules for each scan type
    with SessionLocal() as db:
        from app.db.models import ScanSchedule
        
        default_schedules = [
            {"scan_type": "nse_stocks", "frequency": "daily", "time_of_day": "09:00"},
            {"scan_type": "brst", "frequency": "daily", "time_of_day": "10:00"},
            {"scan_type": "multi_year", "frequency": "weekly", "time_of_day": "10:00"},
            {"scan_type": "golden", "frequency": "daily", "time_of_day": "11:00"},
            {"scan_type": "weekly", "frequency": "weekly", "time_of_day": "11:00"},
            {"scan_type": "darvas", "frequency": "daily", "time_of_day": "10:30"},
            # New choppy-market screeners ship disabled — opt in from Schedule page
            {"scan_type": "mean_reversion", "frequency": "daily", "time_of_day": "10:45", "enabled": False},
            {"scan_type": "vol_squeeze", "frequency": "daily", "time_of_day": "11:15", "enabled": False},
            {"scan_type": "volume_surge", "frequency": "daily", "time_of_day": "16:00", "enabled": False},
            # IPO GMP + subscription scrape (headless browser)
            {"scan_type": "ipo_intel", "frequency": "daily", "time_of_day": "10:15"},
        ]

        for sched in default_schedules:
            existing = db.query(ScanSchedule).filter(
                ScanSchedule.scan_type == sched["scan_type"]
            ).first()
            if existing is None:
                row = ScanSchedule(
                    scan_type=sched["scan_type"],
                    enabled=bool(sched.get("enabled", True)),
                    frequency=sched["frequency"],
                    time_of_day=sched["time_of_day"],
                    timezone="Asia/Kolkata",
                )
                db.add(row)
        
        db.commit()

    logger.info("ScanSchedule and ScanHistory tables migration completed")
    migrate_scan_history_details()


def migrate_scan_history_details() -> None:
    """Add total_scanned and details_json columns to scan_history."""
    import app.db.models as _models  # noqa: F401

    _models.ScanHistory.__table__.create(bind=engine, checkfirst=True)

    insp = inspect(engine)
    if "scan_history" not in insp.get_table_names():
        return

    cols = {c["name"] for c in insp.get_columns("scan_history")}
    with engine.begin() as conn:
        if "total_scanned" not in cols:
            conn.execute(text("ALTER TABLE scan_history ADD COLUMN total_scanned INTEGER"))
        if "details_json" not in cols:
            conn.execute(text("ALTER TABLE scan_history ADD COLUMN details_json TEXT"))

    logger.info("ScanHistory details columns migration completed")


def migrate_ipo_intel_columns() -> None:
    """Add Upstox verification columns to ipo_intel (table created via create_all)."""
    import app.db.models as _models  # noqa: F401

    _models.IpoIntel.__table__.create(bind=engine, checkfirst=True)

    insp = inspect(engine)
    if "ipo_intel" not in insp.get_table_names():
        return

    cols = {c["name"] for c in insp.get_columns("ipo_intel")}
    additions = {
        "upstox_verified": "BOOLEAN DEFAULT FALSE",
        "upstox_symbol": "VARCHAR",
        "isin": "VARCHAR",
        "industry": "VARCHAR",
        "upstox_id": "VARCHAR",
    }
    with engine.begin() as conn:
        for name, ddl in additions.items():
            if name not in cols:
                conn.execute(text(f"ALTER TABLE ipo_intel ADD COLUMN {name} {ddl}"))

    logger.info("ipo_intel Upstox columns migration completed")


def migrate_user_stock_lists() -> None:
    """Create user_stock_lists table for favorites and blacklist."""
    import app.db.models as _models  # noqa: F401

    _models.UserStockListEntry.__table__.create(bind=engine, checkfirst=True)
    logger.info("UserStockListEntry table migration completed")


def migrate_bulk_deals() -> None:
    """Create bulk_deals table for storing NSE large deals data."""
    import app.db.models as _models  # noqa: F401

    _models.BulkDeal.__table__.create(bind=engine, checkfirst=True)

    # Seed a schedule entry for bulk_deals if not present
    with SessionLocal() as db:
        from app.db.models import ScanSchedule

        existing = db.query(ScanSchedule).filter(
            ScanSchedule.scan_type == "bulk_deals"
        ).first()
        if existing is None:
            row = ScanSchedule(
                scan_type="bulk_deals",
                enabled=True,
                frequency="daily",
                time_of_day="19:50",
                timezone="Asia/Kolkata",
            )
            db.add(row)
            db.commit()

    logger.info("BulkDeal table migration completed")


def migrate_sector_rotation() -> None:
    """Create sector_rotation_cache table."""
    import app.db.models as _models  # noqa: F401

    _models.SectorRotationCache.__table__.create(bind=engine, checkfirst=True)

    # Seed a schedule entry for sector_rotation if not present
    with SessionLocal() as db:
        from app.db.models import ScanSchedule

        existing = db.query(ScanSchedule).filter(
            ScanSchedule.scan_type == "sector_rotation"
        ).first()
        if existing is None:
            row = ScanSchedule(
                scan_type="sector_rotation",
                enabled=True,
                frequency="daily",
                time_of_day="18:00",
                timezone="Asia/Kolkata",
            )
            db.add(row)
            db.commit()

    logger.info("SectorRotationCache table migration completed")


# Legacy single-column indexes replaced by explicit composite indexes in models.py.
_REDUNDANT_INDEXES = (
    "ix_stock_prices_daily_symbol",
    "ix_stock_prices_daily_trade_date",
    "ix_financial_cache_symbol",
    "ix_bulk_deals_deal_date",
    "ix_bulk_deals_symbol",
    "ix_ipo_listings_listing_date",
    "ix_live_trades_symbol",
    "ix_live_trade_candidates_symbol",
    "ix_scan_history_scan_type",
)


def migrate_indexes() -> None:
    """Ensure read-optimized indexes exist; drop superseded single-column indexes."""
    import app.db.models as _models  # noqa: F401
    from app.db.database import Base

    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())

    ensured = 0
    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue
        for index in table.indexes:
            index.create(bind=engine, checkfirst=True)
            ensured += 1

    with engine.begin() as conn:
        for name in _REDUNDANT_INDEXES:
            conn.execute(text(f'DROP INDEX IF EXISTS "{name}"'))

    logger.info(
        "Index migration completed (%d table indexes ensured, legacy indexes cleaned up)",
        ensured,
    )
