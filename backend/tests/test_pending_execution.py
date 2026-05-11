"""
Tests for next-candle execution flow.
PAPER TRADING ONLY - NO REAL EXECUTION.
"""

from datetime import datetime, timedelta
from app.schemas.candle import CandleCreate
from app.services.candle_service import upsert_candle, get_next_candle
from app.services.signal_service import save_signal
from app.services.pending_execution_service import (
    create_pending_execution,
    process_pending_executions,
    get_pending_executions,
    cancel_pending_execution,
)
from app.models.pending_execution import PendingExecution
from app.models.trade import PaperTrade
from app.models.position import PaperPosition


# ---------- Helpers ----------

SIGNAL_TS = datetime(2024, 6, 3, 9, 0, 0)   # Monday 9:00
NEXT_TS   = datetime(2024, 6, 3, 10, 0, 0)  # Monday 10:00 — next candle

def _store_candle(db, symbol="RELIANCE", timeframe="1h", ts=SIGNAL_TS, open_=500.0, close=505.0):
    upsert_candle(db, CandleCreate(
        symbol=symbol, timeframe=timeframe, timestamp_utc=ts,
        open=open_, high=close + 5, low=open_ - 5, close=close, volume=50000.0,
    ))

def _buy_signal(db, symbol="RELIANCE", timeframe="1h"):
    return save_signal(
        db, symbol=symbol, timeframe=timeframe,
        strategy_name="ema_rsi_volume", signal_type="BUY",
        candle_timestamp=SIGNAL_TS,
        metadata={"price": 505.0, "stop_loss": 490.0, "target_price": 535.0},
    )

def _hold_signal(db):
    return save_signal(
        db, "TCS", "1h", "ema_rsi_volume", "HOLD", SIGNAL_TS,
    )


# ---------- get_next_candle ----------

def test_get_next_candle_finds_later_candle(db):
    _store_candle(db, ts=SIGNAL_TS, close=505.0)
    _store_candle(db, ts=NEXT_TS, open_=508.0, close=512.0)

    result = get_next_candle(db, "RELIANCE", "1h", after_ts=SIGNAL_TS)
    assert result is not None
    assert result.timestamp_utc == NEXT_TS
    assert result.open == 508.0


def test_get_next_candle_returns_none_when_no_later_candle(db):
    _store_candle(db, ts=SIGNAL_TS)
    result = get_next_candle(db, "RELIANCE", "1h", after_ts=SIGNAL_TS)
    assert result is None


def test_get_next_candle_returns_earliest_next(db):
    ts2 = NEXT_TS
    ts3 = NEXT_TS + timedelta(hours=1)
    _store_candle(db, ts=ts2, open_=508.0)
    _store_candle(db, ts=ts3, open_=515.0)

    result = get_next_candle(db, "RELIANCE", "1h", after_ts=SIGNAL_TS)
    assert result.timestamp_utc == ts2  # returns the earliest, not latest


# ---------- create_pending_execution ----------

def test_create_pending_for_buy_signal(db):
    signal = _buy_signal(db)
    pending = create_pending_execution(db, signal)
    assert pending is not None
    assert pending.status == "PENDING"
    assert pending.signal_id == signal.id
    assert pending.execute_after_timestamp == SIGNAL_TS


def test_create_pending_skips_hold_signal(db):
    signal = _hold_signal(db)
    pending = create_pending_execution(db, signal)
    assert pending is None


def test_create_pending_idempotent(db):
    signal = _buy_signal(db)
    first = create_pending_execution(db, signal)
    second = create_pending_execution(db, signal)  # same signal
    assert first is not None
    assert second is None  # duplicate skipped


# ---------- process_pending_executions ----------

def test_process_waits_when_no_next_candle(db):
    """If next candle hasn't arrived, pending stays PENDING."""
    signal = _buy_signal(db)
    _store_candle(db, ts=SIGNAL_TS)  # only signal candle, no next
    create_pending_execution(db, signal)

    result = process_pending_executions(db)
    assert result["executed"] == 0
    assert result["skipped"] == 1

    pending = db.query(PendingExecution).first()
    assert pending.status == "PENDING"


def test_process_executes_at_next_candle_open(db):
    """Trade must execute at the next candle's OPEN price."""
    signal = _buy_signal(db)
    _store_candle(db, ts=SIGNAL_TS, close=505.0)
    _store_candle(db, ts=NEXT_TS, open_=508.0, close=512.0)  # next candle
    create_pending_execution(db, signal)

    result = process_pending_executions(db)
    assert result["executed"] == 1

    trade = db.query(PaperTrade).filter(PaperTrade.symbol == "RELIANCE").first()
    assert trade is not None
    assert trade.status == "OPEN"
    # Entry price should be near 508.0 (next open) + slippage, NOT 505.0 (signal close)
    assert trade.entry_price > 505.0
    assert abs(trade.entry_price - 508.0 * 1.001) < 0.5


def test_process_marks_pending_executed(db):
    signal = _buy_signal(db)
    _store_candle(db, ts=SIGNAL_TS)
    _store_candle(db, ts=NEXT_TS, open_=508.0)
    create_pending_execution(db, signal)

    process_pending_executions(db)

    pending = db.query(PendingExecution).first()
    assert pending.status == "EXECUTED"


def test_process_cancels_when_position_exists(db):
    """If a position is already open for the symbol, pending is cancelled."""
    # Open an existing position manually
    from app.services.paper_trading import get_or_create_portfolio
    from app.models.position import PaperPosition
    get_or_create_portfolio(db)
    existing = PaperPosition(symbol="RELIANCE", quantity=5, average_price=500.0, unrealized_pnl=0.0)
    db.add(existing)
    db.commit()

    signal = _buy_signal(db)
    _store_candle(db, ts=SIGNAL_TS)
    _store_candle(db, ts=NEXT_TS, open_=508.0)
    create_pending_execution(db, signal)

    result = process_pending_executions(db)
    assert result["cancelled"] == 1

    pending = db.query(PendingExecution).first()
    assert pending.status == "CANCELLED"
    assert "open_position_exists" in (pending.cancel_reason or "")


def test_process_is_idempotent(db):
    """Running process twice should not execute the same pending twice."""
    signal = _buy_signal(db)
    _store_candle(db, ts=SIGNAL_TS)
    _store_candle(db, ts=NEXT_TS, open_=508.0)
    create_pending_execution(db, signal)

    first = process_pending_executions(db)
    second = process_pending_executions(db)

    assert first["executed"] == 1
    assert second["executed"] == 0  # already EXECUTED, not re-processed


def test_cancel_pending_execution(db):
    signal = _buy_signal(db)
    pending = create_pending_execution(db, signal)
    ok = cancel_pending_execution(db, pending.id)
    assert ok is True
    db.refresh(pending)
    assert pending.status == "CANCELLED"


def test_cancel_already_executed_fails(db):
    signal = _buy_signal(db)
    _store_candle(db, ts=SIGNAL_TS)
    _store_candle(db, ts=NEXT_TS, open_=508.0)
    pending = create_pending_execution(db, signal)
    process_pending_executions(db)

    ok = cancel_pending_execution(db, pending.id)
    assert ok is False  # can't cancel an executed pending


# ---------- API tests ----------

def test_list_pending_executions_api(client):
    response = client.get("/api/v1/pending-executions")
    assert response.status_code == 200
    assert isinstance(response.json()["data"], list)


def test_pending_execution_status_api(client):
    response = client.get("/api/v1/pending-executions/status")
    assert response.status_code == 200
    data = response.json()["data"]
    assert "PENDING" in data
    assert "EXECUTED" in data
    assert "CANCELLED" in data


def test_process_pending_api(client):
    response = client.post("/api/v1/pending-executions/process")
    assert response.status_code == 200
    data = response.json()["data"]
    assert "executed" in data
    assert "skipped" in data


def test_cancel_pending_api(client, db):
    signal = save_signal(
        db, "WIPRO", "1h", "ema_rsi_volume", "BUY",
        datetime(2024, 6, 4, 9, 0, 0),
    )
    pending = create_pending_execution(db, signal)
    db.commit()

    response = client.post(f"/api/v1/pending-executions/{pending.id}/cancel")
    assert response.status_code == 200
    assert response.json()["success"] is True
