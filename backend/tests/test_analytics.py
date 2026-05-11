"""Tests for analytics service and API endpoints."""

from datetime import datetime, timedelta
from app.services.analytics_service import (
    get_summary,
    get_equity_curve,
    get_drawdown_curve,
    get_symbol_analytics,
    calculate_streaks,
    calculate_drawdown_series,
)
from app.models.trade import PaperTrade
from app.models.equity_snapshot import EquitySnapshot


# ---------- Helpers ----------

def _add_trade(db, symbol="RELIANCE", pnl=100.0, status="CLOSED", strategy="ema_rsi_volume"):
    t = PaperTrade(
        symbol=symbol, side="BUY", entry_price=500.0, quantity=10.0,
        strategy_name=strategy, status=status, pnl=pnl,
        exit_price=510.0 if pnl > 0 else 490.0,
        created_at=datetime(2024, 6, 1, 9, 0, 0),
        closed_at=datetime(2024, 6, 1, 12, 0, 0),
    )
    db.add(t)
    db.commit()
    return t


def _add_snapshot(db, balance=100000.0, unrealized=0.0, ts=None):
    s = EquitySnapshot(
        timestamp=ts or datetime(2024, 6, 1, 10, 0, 0),
        balance=balance,
        unrealized_pnl=unrealized,
        realized_pnl=0.0,
        drawdown=0.0,
    )
    db.add(s)
    db.commit()
    return s


# ---------- Unit: streak calculation ----------

class _MockTrade:
    def __init__(self, pnl):
        self.pnl = pnl


def _mock_trade(pnl):
    return _MockTrade(pnl)


def test_streaks_empty():
    result = calculate_streaks([])
    assert result["max_win_streak"] == 0
    assert result["current_streak_type"] == "NONE"


def test_streaks_all_wins():
    trades = [_mock_trade(100), _mock_trade(50), _mock_trade(200)]
    result = calculate_streaks(trades)
    assert result["max_win_streak"] == 3
    assert result["current_streak"] == 3
    assert result["current_streak_type"] == "WIN"


def test_streaks_alternating():
    trades = [_mock_trade(100), _mock_trade(-50), _mock_trade(200), _mock_trade(-30)]
    result = calculate_streaks(trades)
    assert result["max_win_streak"] == 1
    assert result["max_loss_streak"] == 1
    assert result["current_streak_type"] == "LOSS"


def test_streaks_win_then_loss_run():
    trades = [_mock_trade(100), _mock_trade(-50), _mock_trade(-30), _mock_trade(-20)]
    result = calculate_streaks(trades)
    assert result["max_loss_streak"] == 3
    assert result["current_streak"] == 3


# ---------- Unit: drawdown calculation ----------

class _MockSnap:
    def __init__(self, balance, unrealized=0.0, minutes_offset=0):
        self.balance = balance
        self.unrealized_pnl = unrealized
        self.timestamp = datetime(2024, 6, 1, 10, 0, 0) + timedelta(minutes=minutes_offset)


def _snap(balance, unrealized=0.0, minutes_offset=0):
    return _MockSnap(balance, unrealized, minutes_offset)


def test_drawdown_empty():
    assert calculate_drawdown_series([]) == []


def test_drawdown_no_decline():
    snaps = [_snap(100000), _snap(101000), _snap(102000)]
    result = calculate_drawdown_series(snaps)
    assert all(r["value"] == 0.0 for r in result)


def test_drawdown_peak_then_decline():
    snaps = [
        _snap(100000, minutes_offset=0),
        _snap(105000, minutes_offset=1),  # new peak
        _snap(100000, minutes_offset=2),  # 4.76% DD from 105000
    ]
    result = calculate_drawdown_series(snaps)
    assert result[0]["value"] == 0.0
    assert result[1]["value"] == 0.0
    assert result[2]["value"] > 4.0


def test_drawdown_recovery():
    snaps = [
        _snap(100000, minutes_offset=0),
        _snap(90000,  minutes_offset=1),  # 10% DD
        _snap(100000, minutes_offset=2),  # back to peak — DD = 0
    ]
    result = calculate_drawdown_series(snaps)
    assert result[1]["value"] == 10.0
    assert result[2]["value"] == 0.0


# ---------- Unit: summary with trades ----------

def test_summary_empty_db(db):
    result = get_summary(db)
    assert result["total_trades"] == 0
    assert result["win_rate"] == 0.0
    assert result["profit_factor"] is None
    assert result["expectancy"] == 0.0


def test_summary_with_trades(db):
    _add_trade(db, pnl=200.0)
    _add_trade(db, pnl=150.0)
    _add_trade(db, pnl=-100.0)

    result = get_summary(db)
    assert result["total_trades"] == 3
    assert result["winning_trades"] == 2
    assert result["losing_trades"] == 1
    assert abs(result["win_rate"] - 0.6667) < 0.001
    assert result["gross_profit"] == 350.0
    assert result["gross_loss"] == 100.0
    assert result["profit_factor"] == 3.5
    assert result["total_realized_pnl"] == 250.0


def test_profit_factor_no_losses(db):
    _add_trade(db, pnl=100.0)
    _add_trade(db, pnl=200.0)
    result = get_summary(db)
    assert result["profit_factor"] is None  # no losses → undefined, not infinite


def test_expectancy_calculation(db):
    # 2 wins of 100 each, 1 loss of 50
    _add_trade(db, pnl=100.0)
    _add_trade(db, pnl=100.0)
    _add_trade(db, pnl=-50.0)
    result = get_summary(db)
    # win_rate = 2/3, avg_win = 100, avg_loss = 50
    # expectancy = (100 * 2/3) - (50 * 1/3) = 66.67 - 16.67 = 50
    assert abs(result["expectancy"] - 50.0) < 1.0


def test_symbol_analytics(db):
    _add_trade(db, symbol="RELIANCE", pnl=100.0)
    _add_trade(db, symbol="RELIANCE", pnl=-50.0)
    _add_trade(db, symbol="TCS", pnl=200.0)

    result = get_symbol_analytics(db)
    symbols = {r["symbol"]: r for r in result}

    assert symbols["RELIANCE"]["total_trades"] == 2
    assert symbols["RELIANCE"]["total_pnl"] == 50.0
    assert symbols["TCS"]["total_trades"] == 1
    assert symbols["TCS"]["total_pnl"] == 200.0


# ---------- API tests ----------

def test_analytics_summary_api(client):
    response = client.get("/api/v1/analytics/summary")
    assert response.status_code == 200
    data = response.json()["data"]
    assert "total_trades" in data
    assert "win_rate" in data
    assert "profit_factor" in data
    assert "max_drawdown_pct" in data


def test_equity_curve_api(client):
    response = client.get("/api/v1/analytics/equity-curve")
    assert response.status_code == 200
    assert isinstance(response.json()["data"], list)


def test_drawdown_api(client):
    response = client.get("/api/v1/analytics/drawdown")
    assert response.status_code == 200
    assert isinstance(response.json()["data"], list)


def test_symbols_api(client):
    response = client.get("/api/v1/analytics/symbols")
    assert response.status_code == 200
    assert isinstance(response.json()["data"], list)


def test_timeframes_api(client):
    response = client.get("/api/v1/analytics/timeframes")
    assert response.status_code == 200
    assert isinstance(response.json()["data"], list)


def test_trade_streaks_api(client):
    response = client.get("/api/v1/analytics/trade-streaks")
    assert response.status_code == 200
    data = response.json()["data"]
    assert "max_win_streak" in data
    assert "current_streak_type" in data


def test_equity_curve_with_snapshots(client, db):
    _add_snapshot(db, balance=100000.0, ts=datetime(2024, 6, 1, 9, 0, 0))
    _add_snapshot(db, balance=101000.0, ts=datetime(2024, 6, 1, 10, 0, 0))

    response = client.get("/api/v1/analytics/equity-curve")
    data = response.json()["data"]
    assert len(data) == 2
    assert data[0]["value"] == 100000.0
    assert data[1]["value"] == 101000.0
