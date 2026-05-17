"""
DB sanity checks against the real PostgreSQL database.

These tests verify the live production schema — they do NOT use the in-memory
SQLite fixture from conftest.py. Run them before Monday market open:

    cd backend
    pytest tests/test_db_sanity.py -v

Each test cleans up after itself. No persistent side effects.
"""

import pytest
from datetime import datetime, timezone
from sqlalchemy import text

# Real production engine + session
from app.db.database import engine, SessionLocal

_REQUIRED_TABLES = [
    "candles", "signals", "paper_trades", "paper_portfolio",
    "paper_positions", "pending_executions", "equity_snapshots",
    "strategies", "watchlists", "scheduler_runs",
]

_REQUIRED_INDEXES = [
    ("candles",            "ix_candles_symbol"),
    ("candles",            "ix_candles_timestamp_utc"),
    ("candles",            "ix_candles_symbol_timeframe"),
    ("signals",            "ix_signals_symbol"),
    ("paper_trades",       "ix_paper_trades_symbol"),
    ("paper_trades",       "ix_paper_trades_signal_id"),
    ("paper_trades",       "ix_paper_trades_symbol_status"),
    ("pending_executions", "ix_pending_executions_symbol"),
    ("pending_executions", "ix_pending_executions_signal_id"),
    ("pending_executions", "ix_pending_executions_status"),
    ("scheduler_runs",     "ix_scheduler_runs_job_id"),
    ("scheduler_runs",     "ix_scheduler_runs_started_at"),
]


@pytest.fixture(scope="module")
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_db_connection():
    """Verify DB is reachable and responds within 2 seconds."""
    import time
    t0 = time.time()
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    elapsed = time.time() - t0
    assert elapsed < 2.0, f"DB too slow: {elapsed:.2f}s"


def test_required_tables_exist():
    """All required tables must be present — indicates migrations are up to date."""
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        ))
        existing = {row[0] for row in result}

    missing = [t for t in _REQUIRED_TABLES if t not in existing]
    assert not missing, (
        f"Missing tables: {missing}. Run: cd backend && alembic upgrade head"
    )


def test_required_indexes_exist():
    """Critical performance indexes must exist."""
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT tablename, indexname FROM pg_indexes WHERE schemaname = 'public'"
        ))
        existing = {(row[0], row[1]) for row in result}

    missing = [(t, i) for t, i in _REQUIRED_INDEXES if (t, i) not in existing]
    assert not missing, f"Missing indexes: {missing}"


def test_candle_insert_read_delete(db):
    """Verify candle table: insert, read back, delete."""
    from app.models.candle import Candle

    now = datetime(2026, 1, 1, 9, 15, 0)
    candle = Candle(
        symbol="SANITY_TEST",
        timeframe="15m",
        timestamp_utc=now,
        open=100.0, high=105.0, low=99.0, close=103.0, volume=1000.0,
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db.add(candle)
    db.commit()

    fetched = db.query(Candle).filter(
        Candle.symbol == "SANITY_TEST", Candle.timeframe == "15m"
    ).first()
    assert fetched is not None
    assert fetched.close == 103.0

    db.delete(fetched)
    db.commit()

    assert db.query(Candle).filter(Candle.symbol == "SANITY_TEST").count() == 0


def test_signal_insert_read_delete(db):
    """Verify signals table: insert, read back, delete."""
    from app.models.signal import Signal

    now = datetime(2026, 1, 1, 9, 15, 0)
    signal = Signal(
        symbol="SANITY_TEST",
        timeframe="15m",
        strategy_name="sanity_check",
        signal_type="BUY",
        candle_timestamp=now,
        generated_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db.add(signal)
    db.commit()

    fetched = db.query(Signal).filter(
        Signal.symbol == "SANITY_TEST", Signal.strategy_name == "sanity_check"
    ).first()
    assert fetched is not None
    assert fetched.signal_type == "BUY"

    db.delete(fetched)
    db.commit()


def test_scheduler_run_insert_read_delete(db):
    """Verify scheduler_runs table: insert, read back, delete."""
    from app.models.scheduler_run import SchedulerRun

    run = SchedulerRun(
        job_id="sanity_test",
        started_at=datetime.now(timezone.utc).replace(tzinfo=None),
        status="COMPLETED",
        symbols_processed=5,
        candles_inserted=75,
        signals_generated=3,
        pending_executed=1,
        errors=0,
    )
    db.add(run)
    db.commit()

    fetched = db.query(SchedulerRun).filter(
        SchedulerRun.job_id == "sanity_test"
    ).first()
    assert fetched is not None
    assert fetched.symbols_processed == 5
    assert fetched.status == "COMPLETED"

    db.delete(fetched)
    db.commit()


def test_unique_constraints_enforced(db):
    """Verify idempotency constraints reject duplicates."""
    from app.models.candle import Candle
    import sqlalchemy.exc

    now = datetime(2026, 1, 2, 9, 15, 0)
    c1 = Candle(
        symbol="SANITY_DUP", timeframe="15m", timestamp_utc=now,
        open=1.0, high=1.0, low=1.0, close=1.0, volume=1.0,
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    c2 = Candle(
        symbol="SANITY_DUP", timeframe="15m", timestamp_utc=now,
        open=2.0, high=2.0, low=2.0, close=2.0, volume=2.0,
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db.add(c1)
    db.commit()

    db.add(c2)
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        db.commit()
    db.rollback()

    # Cleanup
    db.query(Candle).filter(Candle.symbol == "SANITY_DUP").delete()
    db.commit()


def test_portfolio_check_constraint(db):
    """Verify negative virtual_balance is rejected by DB check constraint."""
    from app.models.portfolio import PaperPortfolio
    import sqlalchemy.exc

    bad = PaperPortfolio(
        virtual_balance=-1.0,
        initial_balance=100000.0,
        total_realized_pnl=0.0,
        daily_loss=0.0,
        daily_loss_reset_date=datetime.now(timezone.utc).replace(tzinfo=None),
        updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db.add(bad)
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        db.commit()
    db.rollback()


def test_transaction_rollback(db):
    """Verify rollback leaves no partial state."""
    from app.models.candle import Candle

    now = datetime(2026, 1, 3, 9, 15, 0)
    c = Candle(
        symbol="ROLLBACK_TEST", timeframe="15m", timestamp_utc=now,
        open=1.0, high=1.0, low=1.0, close=1.0, volume=1.0,
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db.add(c)
    db.rollback()

    count = db.query(Candle).filter(Candle.symbol == "ROLLBACK_TEST").count()
    assert count == 0


def test_migration_head():
    """Verify Alembic reports no pending migrations."""
    import subprocess, sys
    from pathlib import Path

    backend_dir = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "current"],
        cwd=str(backend_dir),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"alembic current failed: {result.stderr}"
    assert "(head)" in result.stdout, (
        f"DB is not at migration head. Run: alembic upgrade head\n{result.stdout}"
    )
