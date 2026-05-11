"""
Tests for signal → paper trade execution flow.
PAPER TRADING ONLY - NO REAL EXECUTION.
"""

from datetime import datetime, timedelta
from unittest.mock import patch

from app.services.execution_service import execute_signal, check_and_update_positions, take_equity_snapshot
from app.services.paper_trading import get_or_create_portfolio
from app.services.signal_service import save_signal
from app.models.position import PaperPosition
from app.models.trade import PaperTrade
from app.schemas.candle import CandleCreate


# ---------- Helpers ----------

def _buy_signal(db, symbol="RELIANCE", timeframe="1h", price=500.0, stop=485.0, target=530.0,
                candle_ts=datetime(2024, 6, 1, 9, 0, 0)):
    return save_signal(
        db, symbol=symbol, timeframe=timeframe, strategy_name="ema_rsi_volume",
        signal_type="BUY", candle_timestamp=candle_ts,
        metadata={"price": price, "stop_loss": stop, "target_price": target, "reason": "test"},
    )


def _store_candle(db, symbol="RELIANCE", timeframe="1h", close=500.0):
    from app.services.candle_service import upsert_candle
    upsert_candle(db, CandleCreate(
        symbol=symbol, timeframe=timeframe,
        timestamp_utc=datetime(2024, 6, 1, 9, 0, 0),
        open=close - 5, high=close + 5, low=close - 10, close=close, volume=50000.0,
    ))


# ---------- Unit tests ----------

def test_execute_buy_signal_opens_position(db):
    signal = _buy_signal(db)
    _store_candle(db)

    result = execute_signal(db, signal.id)

    assert result["success"] is True
    trade = result["trade"]
    assert trade.symbol == "RELIANCE"
    assert trade.side == "BUY"
    assert trade.status == "OPEN"
    assert trade.signal_id == signal.id


def test_execute_only_buy_signals(db):
    signal = save_signal(
        db, "RELIANCE", "1h", "ema_rsi_volume", "HOLD",
        datetime(2024, 6, 1, 9, 0, 0),
    )
    result = execute_signal(db, signal.id)
    assert result["success"] is False
    assert "BUY" in result["error"]


def test_duplicate_position_prevention(db):
    """Cannot open a second position for the same symbol."""
    signal1 = _buy_signal(db, candle_ts=datetime(2024, 6, 1, 9, 0, 0))
    signal2 = save_signal(
        db, "RELIANCE", "1h", "ema_rsi_volume", "BUY",
        datetime(2024, 6, 1, 10, 0, 0),
        metadata={"price": 500.0, "stop_loss": 485.0, "target_price": 530.0},
    )
    _store_candle(db)

    first = execute_signal(db, signal1.id)
    assert first["success"] is True

    second = execute_signal(db, signal2.id)
    assert second["success"] is False
    assert "already open" in second["error"]


def test_execute_missing_signal(db):
    result = execute_signal(db, signal_id=9999)
    assert result["success"] is False
    assert "not found" in result["error"]


def test_execute_no_price_data(db):
    signal = _buy_signal(db)
    # No candle stored → no price data
    result = execute_signal(db, signal.id)
    assert result["success"] is False
    assert "price data" in result["error"]


def test_stop_loss_closes_position_as_stopped(db):
    signal = _buy_signal(db, price=500.0, stop=485.0, target=530.0)
    _store_candle(db, close=500.0)
    execute_signal(db, signal.id)

    # Simulate price dropping below stop loss
    _store_candle(db, timeframe="15m", close=480.0)
    result = check_and_update_positions(db)

    assert result["stopped"] == 1
    trade = db.query(PaperTrade).filter(PaperTrade.symbol == "RELIANCE").first()
    assert trade.status == "STOPPED"
    assert trade.pnl is not None and trade.pnl < 0


def test_target_closes_position_as_target_hit(db):
    signal = _buy_signal(db, price=500.0, stop=485.0, target=530.0)
    _store_candle(db, close=500.0)
    execute_signal(db, signal.id)

    # Simulate price hitting target
    _store_candle(db, timeframe="15m", close=535.0)
    result = check_and_update_positions(db)

    assert result["target_hit"] == 1
    trade = db.query(PaperTrade).filter(PaperTrade.symbol == "RELIANCE").first()
    assert trade.status == "TARGET_HIT"
    assert trade.pnl is not None and trade.pnl > 0


def test_portfolio_balance_updates_after_trade(db):
    signal = _buy_signal(db)
    _store_candle(db)
    portfolio = get_or_create_portfolio(db)
    before = portfolio.virtual_balance

    execute_signal(db, signal.id)

    db.refresh(portfolio)
    assert portfolio.virtual_balance < before  # balance decreased by trade cost


def test_portfolio_balance_restores_after_target(db):
    signal = _buy_signal(db, price=500.0, stop=485.0, target=530.0)
    _store_candle(db, close=500.0)
    execute_signal(db, signal.id)
    portfolio = get_or_create_portfolio(db)
    after_entry = portfolio.virtual_balance

    _store_candle(db, timeframe="15m", close=535.0)
    check_and_update_positions(db)

    db.refresh(portfolio)
    assert portfolio.virtual_balance > after_entry  # balance increased after profit


def test_equity_snapshot_saved(db):
    snapshot = take_equity_snapshot(db)
    assert snapshot.id is not None
    assert snapshot.balance == 100000.0
    assert snapshot.drawdown == 0.0


# ---------- API tests ----------

def test_execute_via_api(client, db):
    from app.models.signal import Signal
    signal = save_signal(
        db, "TCS", "1h", "ema_rsi_volume", "BUY",
        datetime(2024, 6, 1, 9, 0, 0),
        metadata={"price": 3500.0, "stop_loss": 3395.0, "target_price": 3710.0},
    )
    from app.services.candle_service import upsert_candle
    upsert_candle(db, CandleCreate(
        symbol="TCS", timeframe="1h",
        timestamp_utc=datetime(2024, 6, 1, 9, 0, 0),
        open=3490.0, high=3520.0, low=3480.0, close=3500.0, volume=20000.0,
    ))
    db.commit()

    response = client.post(f"/api/v1/paper-trades/execute/{signal.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["symbol"] == "TCS"
    assert data["data"]["status"] == "OPEN"
    assert data["data"]["signal_id"] == signal.id


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
