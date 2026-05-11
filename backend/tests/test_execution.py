"""
Tests for paper trade execution flow.
PAPER TRADING ONLY - NO REAL EXECUTION.

Entry execution routes exclusively through pending_execution_service (next-candle flow).
Each test that needs a trade to open must store both the signal candle and the next candle.
"""

from datetime import datetime

from app.services.pending_execution_service import create_pending_execution, process_pending_executions
from app.services.execution_service import check_and_update_positions, take_equity_snapshot
from app.services.paper_trading import get_or_create_portfolio
from app.services.signal_service import save_signal
from app.models.position import PaperPosition
from app.models.trade import PaperTrade
from app.models.pending_execution import PendingExecution
from app.schemas.candle import CandleCreate


# ---------- Helpers ----------

def _buy_signal(db, symbol="RELIANCE", timeframe="1h", price=500.0, stop=485.0, target=530.0,
                candle_ts=datetime(2024, 6, 1, 9, 0, 0)):
    return save_signal(
        db, symbol=symbol, timeframe=timeframe, strategy_name="ema_rsi_volume",
        signal_type="BUY", candle_timestamp=candle_ts,
        metadata={"price": price, "stop_loss": stop, "target_price": target, "reason": "test"},
    )


def _store_candle(db, symbol="RELIANCE", timeframe="1h", close=500.0,
                  ts=datetime(2024, 6, 1, 9, 0, 0)):
    from app.services.candle_service import upsert_candle
    upsert_candle(db, CandleCreate(
        symbol=symbol, timeframe=timeframe,
        timestamp_utc=ts,
        open=close - 5, high=close + 5, low=close - 10, close=close, volume=50000.0,
    ))


def _execute_via_pending(db, signal):
    """Queue a pending execution and immediately process it. Returns the created trade or None."""
    create_pending_execution(db, signal)
    process_pending_executions(db)
    return db.query(PaperTrade).filter(PaperTrade.signal_id == signal.id).first()


# ---------- Unit tests ----------

def test_execute_buy_signal_opens_position(db):
    signal = _buy_signal(db)
    _store_candle(db)                                            # signal candle
    _store_candle(db, ts=datetime(2024, 6, 1, 10, 0, 0))        # next candle (execution price)

    trade = _execute_via_pending(db, signal)

    assert trade is not None
    assert trade.symbol == "RELIANCE"
    assert trade.side == "BUY"
    assert trade.status == "OPEN"
    assert trade.signal_id == signal.id


def test_execute_only_buy_signals(db):
    """Non-BUY signals are not queued for execution."""
    signal = save_signal(
        db, "RELIANCE", "1h", "ema_rsi_volume", "HOLD",
        datetime(2024, 6, 1, 9, 0, 0),
    )
    pending = create_pending_execution(db, signal)
    assert pending is None


def test_duplicate_position_prevention(db):
    """Second pending execution for same symbol is cancelled when position already open."""
    signal1 = _buy_signal(db, candle_ts=datetime(2024, 6, 1, 9, 0, 0))
    signal2 = save_signal(
        db, "RELIANCE", "1h", "ema_rsi_volume", "BUY",
        datetime(2024, 6, 1, 10, 0, 0),
        metadata={"price": 500.0, "stop_loss": 485.0, "target_price": 530.0},
    )
    _store_candle(db, ts=datetime(2024, 6, 1, 9, 0, 0))   # signal1 candle
    _store_candle(db, ts=datetime(2024, 6, 1, 10, 0, 0))  # next candle for signal1 / signal2 candle
    _store_candle(db, ts=datetime(2024, 6, 1, 11, 0, 0))  # next candle for signal2

    trade1 = _execute_via_pending(db, signal1)
    assert trade1 is not None

    create_pending_execution(db, signal2)
    process_pending_executions(db)

    pe2 = db.query(PendingExecution).filter(PendingExecution.signal_id == signal2.id).first()
    assert pe2.status == "CANCELLED"
    assert "open_position_exists" in pe2.cancel_reason


def test_execution_waits_for_next_candle(db):
    """Without a next candle, pending execution stays PENDING."""
    signal = _buy_signal(db)
    # No candles stored — next candle not available
    create_pending_execution(db, signal)
    process_pending_executions(db)

    trade = db.query(PaperTrade).filter(PaperTrade.signal_id == signal.id).first()
    assert trade is None

    pe = db.query(PendingExecution).filter(PendingExecution.signal_id == signal.id).first()
    assert pe.status == "PENDING"


def test_stop_loss_closes_position_as_stopped(db):
    signal = _buy_signal(db, price=500.0, stop=485.0, target=530.0)
    _store_candle(db, close=500.0)
    _store_candle(db, ts=datetime(2024, 6, 1, 10, 0, 0), close=500.0)
    _execute_via_pending(db, signal)

    _store_candle(db, timeframe="15m", ts=datetime(2024, 6, 1, 10, 15, 0), close=480.0)
    result = check_and_update_positions(db)

    assert result["stopped"] == 1
    trade = db.query(PaperTrade).filter(PaperTrade.symbol == "RELIANCE").first()
    assert trade.status == "STOPPED"
    assert trade.pnl is not None and trade.pnl < 0


def test_target_closes_position_as_target_hit(db):
    signal = _buy_signal(db, price=500.0, stop=485.0, target=530.0)
    _store_candle(db, close=500.0)
    _store_candle(db, ts=datetime(2024, 6, 1, 10, 0, 0), close=500.0)
    _execute_via_pending(db, signal)

    _store_candle(db, timeframe="15m", ts=datetime(2024, 6, 1, 10, 15, 0), close=535.0)
    result = check_and_update_positions(db)

    assert result["target_hit"] == 1
    trade = db.query(PaperTrade).filter(PaperTrade.symbol == "RELIANCE").first()
    assert trade.status == "TARGET_HIT"
    assert trade.pnl is not None and trade.pnl > 0


def test_portfolio_balance_updates_after_trade(db):
    signal = _buy_signal(db)
    _store_candle(db)
    _store_candle(db, ts=datetime(2024, 6, 1, 10, 0, 0))
    portfolio = get_or_create_portfolio(db)
    before = portfolio.virtual_balance

    _execute_via_pending(db, signal)

    db.refresh(portfolio)
    assert portfolio.virtual_balance < before


def test_portfolio_balance_restores_after_target(db):
    signal = _buy_signal(db, price=500.0, stop=485.0, target=530.0)
    _store_candle(db, close=500.0)
    _store_candle(db, ts=datetime(2024, 6, 1, 10, 0, 0), close=500.0)
    _execute_via_pending(db, signal)
    portfolio = get_or_create_portfolio(db)
    after_entry = portfolio.virtual_balance

    _store_candle(db, timeframe="15m", ts=datetime(2024, 6, 1, 10, 15, 0), close=535.0)
    check_and_update_positions(db)

    db.refresh(portfolio)
    assert portfolio.virtual_balance > after_entry


def test_equity_snapshot_saved(db):
    snapshot = take_equity_snapshot(db)
    assert snapshot.id is not None
    assert snapshot.balance == 100000.0
    assert snapshot.drawdown == 0.0


# ---------- API tests ----------

def test_execute_via_api(client, db):
    from app.services.candle_service import upsert_candle
    signal = save_signal(
        db, "TCS", "1h", "ema_rsi_volume", "BUY",
        datetime(2024, 6, 1, 9, 0, 0),
        metadata={"price": 3500.0, "stop_loss": 3395.0, "target_price": 3710.0},
    )
    upsert_candle(db, CandleCreate(
        symbol="TCS", timeframe="1h",
        timestamp_utc=datetime(2024, 6, 1, 9, 0, 0),
        open=3490.0, high=3520.0, low=3480.0, close=3500.0, volume=20000.0,
    ))
    upsert_candle(db, CandleCreate(
        symbol="TCS", timeframe="1h",
        timestamp_utc=datetime(2024, 6, 1, 10, 0, 0),
        open=3510.0, high=3530.0, low=3500.0, close=3510.0, volume=18000.0,
    ))
    db.commit()

    response = client.post(f"/api/v1/paper-trades/execute/{signal.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["symbol"] == "TCS"
    assert data["data"]["status"] == "OPEN"
    assert data["data"]["signal_id"] == signal.id


def test_execute_missing_signal(client):
    response = client.post("/api/v1/paper-trades/execute/9999")
    assert response.status_code == 404


def test_execute_non_buy_signal(client, db):
    signal = save_signal(
        db, "RELIANCE", "1h", "ema_rsi_volume", "HOLD",
        datetime(2024, 6, 1, 9, 0, 0),
    )
    db.commit()
    response = client.post(f"/api/v1/paper-trades/execute/{signal.id}")
    assert response.status_code == 400


def test_list_paper_trades(client):
    response = client.get("/api/v1/paper-trades")
    assert response.status_code == 200
    assert isinstance(response.json()["data"], list)


def test_list_paper_positions(client):
    response = client.get("/api/v1/paper-positions")
    assert response.status_code == 200
    assert isinstance(response.json()["data"], list)


def test_portfolio_endpoint(client):
    response = client.get("/api/v1/portfolio")
    assert response.status_code == 200
    data = response.json()["data"]
    assert "virtual_balance" in data
    assert data["virtual_balance"] == 100000.0


def test_equity_curve_endpoint(client):
    response = client.get("/api/v1/portfolio/equity-curve")
    assert response.status_code == 200
    assert isinstance(response.json()["data"], list)


def test_close_position_via_api(client, db):
    from app.services.candle_service import upsert_candle
    signal = save_signal(
        db, "INFY", "1h", "ema_rsi_volume", "BUY",
        datetime(2024, 6, 1, 9, 0, 0),
        metadata={"price": 1500.0, "stop_loss": 1455.0, "target_price": 1590.0},
    )
    upsert_candle(db, CandleCreate(
        symbol="INFY", timeframe="1h",
        timestamp_utc=datetime(2024, 6, 1, 9, 0, 0),
        open=1495.0, high=1510.0, low=1490.0, close=1500.0, volume=30000.0,
    ))
    upsert_candle(db, CandleCreate(
        symbol="INFY", timeframe="1h",
        timestamp_utc=datetime(2024, 6, 1, 10, 0, 0),
        open=1505.0, high=1520.0, low=1500.0, close=1505.0, volume=25000.0,
    ))
    db.commit()

    client.post(f"/api/v1/paper-trades/execute/{signal.id}")

    position = db.query(PaperPosition).filter(PaperPosition.symbol == "INFY").first()
    assert position is not None

    response = client.post(
        f"/api/v1/paper-trades/close/{position.id}",
        json={"symbol": "INFY", "price": 1520.0},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "CLOSED"
