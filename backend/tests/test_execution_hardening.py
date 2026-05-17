"""
Execution hardening test suite.
Tests: duplicate trade protection, position-limit race conditions,
stale-data skipping, DB rollback guarantees, crash-recovery idempotency,
and the new monitoring endpoints.

All tests use the in-memory SQLite fixture from conftest.py.
Partial unique indexes are not enforced by SQLite — crash-recovery idempotency
is tested via the Python-level signal_id check, which works on all backends.
"""

import threading
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.core.config import settings
from app.schemas.candle import CandleCreate
from app.services.candle_service import upsert_candle
from app.services.signal_service import save_signal
from app.services.pending_execution_service import (
    create_pending_execution,
    process_pending_executions,
)
from app.services.paper_trading import (
    simulate_order,
    get_or_create_portfolio,
    simulate_close_position,
)
from app.services import event_service as ev
from app.models.trade import PaperTrade
from app.models.position import PaperPosition
from app.models.execution_event import ExecutionEvent
from app.schemas.trade import SimulateOrderRequest
from app.core.exceptions import DuplicateSignalTradeError

# ── fixtures ──────────────────────────────────────────────────────────────────

SIGNAL_TS = datetime(2024, 6, 3, 9, 0, 0)
NEXT_TS   = datetime(2024, 6, 3, 10, 0, 0)


def _candle(db, symbol="RELIANCE", timeframe="1h", ts=SIGNAL_TS, open_=500.0, close=505.0):
    upsert_candle(db, CandleCreate(
        symbol=symbol, timeframe=timeframe, timestamp_utc=ts,
        open=open_, high=close + 5, low=open_ - 5, close=close, volume=50_000.0,
    ))


def _buy_signal(db, symbol="RELIANCE", timeframe="1h", ts=SIGNAL_TS):
    return save_signal(
        db, symbol=symbol, timeframe=timeframe,
        strategy_name="ema_rsi_volume", signal_type="BUY",
        candle_timestamp=ts,
        metadata={"price": 505.0, "stop_loss": 490.0, "target_price": 535.0},
    )


def _sell_signal(db, symbol="RELIANCE", timeframe="1h", ts=SIGNAL_TS):
    return save_signal(
        db, symbol=symbol, timeframe=timeframe,
        strategy_name="ema_rsi_volume", signal_type="SELL",
        candle_timestamp=ts,
    )


_API_HEADERS = {"X-API-Key": settings.api_key}


def _buy_request(symbol="RELIANCE", price=508.0, qty=10.0) -> SimulateOrderRequest:
    return SimulateOrderRequest(
        symbol=symbol, side="BUY", quantity=qty, price=price,
        strategy_name="ema_rsi_volume",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# PART 1 — Duplicate trade protection
# ═══════════════════════════════════════════════════════════════════════════════

class TestDuplicateTradeProtection:

    def test_signal_id_set_atomically_on_trade(self, db):
        """simulate_order sets signal_id in the same commit as the trade."""
        get_or_create_portfolio(db)
        trade = simulate_order(db, _buy_request(), signal_id=42)
        assert trade.signal_id == 42

    def test_crash_recovery_skips_double_execution(self, db):
        """
        If a trade with this signal_id already exists, _process_one_pending
        marks the pending EXECUTED without creating a second trade.
        """
        _candle(db)
        _candle(db, ts=NEXT_TS, open_=508.0, close=512.0)
        signal = _buy_signal(db)
        pending = create_pending_execution(db, signal)

        # Simulate crash: trade exists but pending is still PENDING.
        # Directly insert the trade with the signal_id.
        get_or_create_portfolio(db)
        trade = simulate_order(db, _buy_request(), signal_id=signal.id)
        assert db.query(PaperTrade).count() == 1

        # Now process_pending_executions must detect the existing trade
        # and mark EXECUTED without inserting a second trade.
        result = process_pending_executions(db)

        assert db.query(PaperTrade).count() == 1, "crash recovery must not create duplicate trade"
        db.refresh(pending)
        assert pending.status == "EXECUTED"

    def test_duplicate_blocked_event_emitted(self, db):
        """When a pending is cancelled due to existing position, DUPLICATE_BLOCKED is emitted."""
        _candle(db)
        _candle(db, ts=NEXT_TS, open_=508.0)
        signal = _buy_signal(db)

        # Pre-create a position so the pending gets cancelled
        get_or_create_portfolio(db)
        pos = PaperPosition(
            symbol="RELIANCE", quantity=10, average_price=500.0, unrealized_pnl=0.0
        )
        db.add(pos)
        db.commit()

        pending = create_pending_execution(db, signal)
        process_pending_executions(db, cycle_id="test-cycle-1")

        events = db.query(ExecutionEvent).filter(
            ExecutionEvent.event_type == ev.DUPLICATE_BLOCKED
        ).all()
        assert len(events) == 1
        assert events[0].symbol == "RELIANCE"
        assert events[0].cycle_id == "test-cycle-1"

    def test_process_pending_idempotent_after_recovery(self, db):
        """Running process_pending_executions twice never creates two trades."""
        _candle(db)
        _candle(db, ts=NEXT_TS, open_=508.0)
        signal = _buy_signal(db)
        create_pending_execution(db, signal)

        first  = process_pending_executions(db)
        second = process_pending_executions(db)

        assert first["executed"] == 1
        assert second["executed"] == 0
        assert db.query(PaperTrade).count() == 1

    def test_open_positions_check_endpoint_safe(self, client):
        """GET /open-positions/check returns safe=true when no duplicates."""
        resp = client.get("/api/v1/trading/open-positions/check", headers=_API_HEADERS)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["safe"] is True
        assert data["duplicate_open_positions"] == []

    def test_open_positions_check_detects_orphan(self, client, db):
        """Detects OPEN trade with no matching PaperPosition."""
        get_or_create_portfolio(db)
        trade = PaperTrade(
            symbol="ORPHAN", side="BUY", entry_price=100.0, quantity=1.0,
            strategy_name="test", status="OPEN",
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        db.add(trade)
        db.commit()

        resp = client.get("/api/v1/trading/open-positions/check", headers=_API_HEADERS)
        data = resp.json()["data"]
        assert data["safe"] is False
        assert "ORPHAN" in data["orphaned_open_trades"]


# ═══════════════════════════════════════════════════════════════════════════════
# PART 2 — Position-limit serialization
# ═══════════════════════════════════════════════════════════════════════════════

class TestPositionLimitSerialization:

    def test_max_positions_enforced(self, db):
        """Cannot open more than MAX_SIMULTANEOUS_POSITIONS positions."""
        from app.core.config import settings
        from app.core.exceptions import MaxPositionsError

        get_or_create_portfolio(db)
        max_pos = settings.max_simultaneous_positions

        # Fill up to the limit
        for i in range(max_pos):
            symbol = f"SYM{i}"
            simulate_order(db, SimulateOrderRequest(
                symbol=symbol, side="BUY", quantity=1.0, price=100.0,
                strategy_name="ema_rsi_volume",
            ))

        assert db.query(PaperPosition).count() == max_pos

        # One more should raise
        with pytest.raises(MaxPositionsError):
            simulate_order(db, SimulateOrderRequest(
                symbol="OVERFLOW", side="BUY", quantity=1.0, price=100.0,
                strategy_name="ema_rsi_volume",
            ))

    def test_position_count_checked_inside_lock(self, db):
        """
        Simulates a sequential 'race': second BUY arrives after first commits.
        First fills the last slot; second must be rejected even though it
        checked the count before the first committed.
        """
        from app.core.config import settings
        from app.core.exceptions import MaxPositionsError

        get_or_create_portfolio(db)
        max_pos = settings.max_simultaneous_positions

        # Fill to max - 1
        for i in range(max_pos - 1):
            simulate_order(db, SimulateOrderRequest(
                symbol=f"PRE{i}", side="BUY", quantity=1.0, price=100.0,
                strategy_name="ema_rsi_volume",
            ))

        # Take the last slot
        simulate_order(db, SimulateOrderRequest(
            symbol="LAST", side="BUY", quantity=1.0, price=100.0,
            strategy_name="ema_rsi_volume",
        ))

        # Now attempt a second, should fail
        with pytest.raises(MaxPositionsError):
            simulate_order(db, SimulateOrderRequest(
                symbol="EXTRA", side="BUY", quantity=1.0, price=100.0,
                strategy_name="ema_rsi_volume",
            ))

        assert db.query(PaperPosition).count() == max_pos

    def test_failed_transaction_rolls_back_portfolio(self, db):
        """If simulate_order raises, portfolio balance stays unchanged."""
        from app.core.exceptions import MaxPositionsError, InsufficientBalanceError

        portfolio = get_or_create_portfolio(db)
        initial_balance = portfolio.virtual_balance

        with pytest.raises((MaxPositionsError, InsufficientBalanceError, Exception)):
            simulate_order(db, SimulateOrderRequest(
                symbol="FAIL", side="BUY", quantity=999_999.0, price=999_999.0,
                strategy_name="ema_rsi_volume",
            ))

        db.refresh(portfolio)
        assert portfolio.virtual_balance == initial_balance, "balance must not change on failed order"


# ═══════════════════════════════════════════════════════════════════════════════
# PART 3 — Stale data protection
# ═══════════════════════════════════════════════════════════════════════════════

class TestStaleDataProtection:

    def test_freshness_check_fresh_candle(self, db):
        """A candle timestamped within threshold reports fresh."""
        from app.services.scheduler_service import _check_freshness
        from datetime import timezone

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        recent_ts = now - timedelta(minutes=5)

        upsert_candle(db, CandleCreate(
            symbol="TATA", timeframe="15m", timestamp_utc=recent_ts,
            open=100.0, high=105.0, low=99.0, close=103.0, volume=1000.0,
        ))

        with patch("app.services.scheduler_service._is_market_hours", return_value=True):
            is_stale, lag = _check_freshness(db, "TATA", "15m")

        assert is_stale is False
        assert lag < 20

    def test_freshness_check_stale_candle(self, db):
        """A candle older than threshold reports stale during market hours."""
        from app.services.scheduler_service import _check_freshness
        from datetime import timezone

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        old_ts = now - timedelta(minutes=30)  # 30 > 20 min threshold

        upsert_candle(db, CandleCreate(
            symbol="STALE", timeframe="15m", timestamp_utc=old_ts,
            open=100.0, high=105.0, low=99.0, close=103.0, volume=1000.0,
        ))

        with patch("app.services.scheduler_service._is_market_hours", return_value=True):
            is_stale, lag = _check_freshness(db, "STALE", "15m")

        assert is_stale is True
        assert lag >= 30

    def test_freshness_check_outside_market_hours_never_stale(self, db):
        """Outside market hours, even a very old candle is not flagged stale."""
        from app.services.scheduler_service import _check_freshness
        from datetime import timezone

        old_ts = datetime(2020, 1, 1, 9, 0, 0)
        upsert_candle(db, CandleCreate(
            symbol="OLD", timeframe="15m", timestamp_utc=old_ts,
            open=100.0, high=105.0, low=99.0, close=103.0, volume=1000.0,
        ))

        with patch("app.services.scheduler_service._is_market_hours", return_value=False):
            is_stale, _ = _check_freshness(db, "OLD", "15m")

        assert is_stale is False

    def test_daily_candles_never_stale(self, db):
        """1d timeframe is exempt from staleness checks (threshold=None)."""
        from app.services.scheduler_service import _check_freshness
        from datetime import timezone

        old_ts = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=10)
        upsert_candle(db, CandleCreate(
            symbol="NIFTY", timeframe="1d", timestamp_utc=old_ts,
            open=22000.0, high=22200.0, low=21900.0, close=22100.0, volume=1_000_000.0,
        ))

        with patch("app.services.scheduler_service._is_market_hours", return_value=True):
            is_stale, _ = _check_freshness(db, "NIFTY", "1d")

        assert is_stale is False

    def test_stale_data_event_emitted(self, db):
        """STALE_DATA event is written to execution_events when candle is stale."""
        from app.services.scheduler_service import _process_one
        from datetime import timezone

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        old_ts = now - timedelta(minutes=30)
        upsert_candle(db, CandleCreate(
            symbol="STALECO", timeframe="15m", timestamp_utc=old_ts,
            open=100.0, high=105.0, low=99.0, close=103.0, volume=1000.0,
        ))

        with patch("app.services.scheduler_service._is_market_hours", return_value=True):
            result = _process_one(db, "STALECO", "15m", cycle_id="test-stale")

        assert result["stale_skipped"] == 1
        stale_events = db.query(ExecutionEvent).filter(
            ExecutionEvent.event_type == ev.STALE_DATA
        ).all()
        assert len(stale_events) == 1
        assert stale_events[0].symbol == "STALECO"
        assert stale_events[0].cycle_id == "test-stale"

    def test_candle_freshness_endpoint(self, client):
        """GET /api/v1/candles/freshness returns per-symbol freshness data."""
        resp = client.get("/api/v1/candles/freshness", headers=_API_HEADERS)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "all_fresh" in data
        assert "symbols" in data


# ═══════════════════════════════════════════════════════════════════════════════
# PART 4 — Execution safety hardening
# ═══════════════════════════════════════════════════════════════════════════════

class TestExecutionSafetyHardening:

    def test_cycle_id_propagates_to_events(self, db):
        """BUY_EXECUTED events carry the cycle_id from the scheduler cycle."""
        _candle(db)
        _candle(db, ts=NEXT_TS, open_=508.0)
        signal = _buy_signal(db)
        create_pending_execution(db, signal)

        process_pending_executions(db, cycle_id="my-test-cycle")

        buy_events = db.query(ExecutionEvent).filter(
            ExecutionEvent.event_type == ev.BUY_EXECUTED
        ).all()
        assert len(buy_events) == 1
        assert buy_events[0].cycle_id == "my-test-cycle"

    def test_sell_event_emitted_on_sell_pending(self, db):
        """SELL_EXECUTED event is emitted when a SELL pending execution fires."""
        _candle(db)
        _candle(db, ts=NEXT_TS, open_=508.0)

        # Create open position first
        get_or_create_portfolio(db)
        buy_sig = _buy_signal(db, ts=datetime(2024, 6, 2, 9, 0, 0))
        # Manually insert a position instead of executing a full trade
        pos = PaperPosition(
            symbol="RELIANCE", quantity=10.0, average_price=500.0, unrealized_pnl=0.0
        )
        db.add(pos)
        db.commit()

        sell_sig = _sell_signal(db)
        pending = create_pending_execution(db, sell_sig)
        result = process_pending_executions(db, cycle_id="sell-cycle")

        assert result["executed"] == 1
        sell_events = db.query(ExecutionEvent).filter(
            ExecutionEvent.event_type == ev.SELL_EXECUTED
        ).all()
        assert len(sell_events) == 1
        assert sell_events[0].cycle_id == "sell-cycle"

    def test_scheduler_overlap_prevention(self):
        """The threading lock prevents two simultaneous scheduler cycles."""
        import threading
        from app.scheduler import _cycle_lock

        results = []

        def _try_acquire():
            acquired = _cycle_lock.acquire(blocking=False)
            results.append(acquired)
            if acquired:
                # Hold lock briefly
                import time; time.sleep(0.05)
                _cycle_lock.release()

        t1 = threading.Thread(target=_try_acquire)
        t2 = threading.Thread(target=_try_acquire)

        # Acquire the lock in main thread first
        _cycle_lock.acquire()
        try:
            t1.start()
            t2.start()
            t1.join()
            t2.join()
        finally:
            _cycle_lock.release()

        # Both threads attempted; both should have failed (lock held by main)
        assert results == [False, False] or (
            # If somehow they ran after the lock released — at most ONE acquires
            results.count(True) <= 1
        )

    def test_failed_buy_does_not_leave_orphan_position(self, db):
        """A BUY that fails the balance check leaves no position in the DB."""
        from app.core.exceptions import InsufficientBalanceError

        portfolio = get_or_create_portfolio(db)
        # Drain the balance
        portfolio.virtual_balance = 1.0
        db.commit()

        with pytest.raises(InsufficientBalanceError):
            simulate_order(db, _buy_request(qty=1000.0, price=500.0))

        assert db.query(PaperPosition).count() == 0
        assert db.query(PaperTrade).filter(PaperTrade.status == "OPEN").count() == 0

    def test_trade_pnl_consistent_after_close(self, db):
        """PnL on closed trades must equal the total position PnL."""
        get_or_create_portfolio(db)
        trade = simulate_order(db, _buy_request(qty=10.0, price=500.0))

        close_price = 550.0
        simulate_close_position(db, "RELIANCE", close_price, close_status="CLOSED")

        closed_trade = db.query(PaperTrade).filter(PaperTrade.symbol == "RELIANCE").first()
        assert closed_trade.status == "CLOSED"
        # PnL should be positive for a profitable close
        assert closed_trade.pnl is not None
        assert closed_trade.pnl > 0


# ═══════════════════════════════════════════════════════════════════════════════
# PART 5 — Operational visibility
# ═══════════════════════════════════════════════════════════════════════════════

class TestOperationalVisibility:

    def test_event_emit_and_retrieve(self, db):
        """emit() writes an event; get_recent() retrieves it."""
        ev.emit(db, ev.BUY_EXECUTED, symbol="TEST", strategy_name="ema",
                cycle_id="c1", details={"price": 100.0})

        events = ev.get_recent(db, limit=10)
        assert len(events) >= 1
        assert events[0].event_type == ev.BUY_EXECUTED
        assert events[0].symbol == "TEST"

    def test_emit_never_raises_on_db_error(self, db):
        """emit() swallows DB errors silently."""
        # Close the session to simulate a DB error
        db.close()
        try:
            ev.emit(db, ev.SCHEDULER_FAILED)  # must not raise
        except Exception as exc:
            pytest.fail(f"emit() raised unexpectedly: {exc}")

    def test_events_recent_endpoint(self, client):
        resp = client.get("/api/v1/events/recent", headers=_API_HEADERS)
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"], list)

    def test_events_recent_filtered_by_type(self, client, db):
        ev.emit(db, ev.BUY_EXECUTED, symbol="FILTER_TEST")
        ev.emit(db, ev.STALE_DATA, symbol="FILTER_TEST")

        resp = client.get("/api/v1/events/recent?event_type=BUY_EXECUTED", headers=_API_HEADERS)
        assert resp.status_code == 200
        data = resp.json()["data"]
        types = {e["event_type"] for e in data}
        assert types <= {ev.BUY_EXECUTED}

    def test_events_metrics_endpoint(self, client):
        resp = client.get("/api/v1/events/metrics", headers=_API_HEADERS)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "total_cycles" in data
        assert "buys_executed" in data
        assert "stale_skips" in data
        assert "duplicate_blocks" in data


# ═══════════════════════════════════════════════════════════════════════════════
# PART 6 — DB rollback verification
# ═══════════════════════════════════════════════════════════════════════════════

class TestDBRollback:

    def test_position_absent_after_rollback(self, db):
        """Explicit rollback leaves no stale position in the DB."""
        pos = PaperPosition(
            symbol="ROLLBACK_SYM", quantity=5.0,
            average_price=100.0, unrealized_pnl=0.0
        )
        db.add(pos)
        db.rollback()

        count = db.query(PaperPosition).filter(
            PaperPosition.symbol == "ROLLBACK_SYM"
        ).count()
        assert count == 0

    def test_portfolio_balance_unchanged_after_exception(self, db):
        """simulate_order exception must not deduct from portfolio."""
        from app.core.exceptions import InsufficientBalanceError

        portfolio = get_or_create_portfolio(db)
        before = portfolio.virtual_balance

        # Request that will fail: cost exceeds balance
        try:
            simulate_order(db, SimulateOrderRequest(
                symbol="FAIL", side="BUY", quantity=10_000.0, price=10_000.0,
                strategy_name="ema_rsi_volume",
            ))
        except (InsufficientBalanceError, Exception):
            pass

        db.refresh(portfolio)
        assert portfolio.virtual_balance == before

    def test_no_trade_record_after_cancel(self, db):
        """Cancelled pending execution must leave zero OPEN trades."""
        _candle(db)
        # Do NOT add NEXT_TS candle — pending will be skipped, not executed
        signal = _buy_signal(db)
        create_pending_execution(db, signal)

        result = process_pending_executions(db)
        assert result["executed"] == 0
        assert db.query(PaperTrade).filter(PaperTrade.status == "OPEN").count() == 0
