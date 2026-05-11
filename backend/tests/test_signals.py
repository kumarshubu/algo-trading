"""Tests for signal persistence, idempotency, and API endpoints."""

from datetime import datetime
from unittest.mock import patch

from app.services.signal_service import save_signal, get_latest_signal, get_recent_signals


# ---------- signal_service unit tests ----------

def test_save_signal(db):
    s = save_signal(
        db, symbol="RELIANCE", timeframe="1h", strategy_name="ema_rsi_volume",
        signal_type="BUY", candle_timestamp=datetime(2024, 6, 1, 10, 0, 0),
        metadata={"price": 2500.0, "reason": "test"},
    )
    assert s is not None
    assert s.symbol == "RELIANCE"
    assert s.signal_type == "BUY"


def test_duplicate_signal_skipped(db):
    ts = datetime(2024, 6, 1, 10, 0, 0)
    first = save_signal(db, "RELIANCE", "1h", "ema_rsi_volume", "BUY", ts)
    second = save_signal(db, "RELIANCE", "1h", "ema_rsi_volume", "BUY", ts)
    assert first is not None
    assert second is None  # duplicate skipped


def test_different_candle_timestamps_allowed(db):
    first = save_signal(db, "RELIANCE", "1h", "ema_rsi_volume", "BUY", datetime(2024, 6, 1, 9, 0, 0))
    second = save_signal(db, "RELIANCE", "1h", "ema_rsi_volume", "BUY", datetime(2024, 6, 1, 10, 0, 0))
    assert first is not None
    assert second is not None  # different timestamp — allowed


def test_different_symbols_allowed(db):
    ts = datetime(2024, 6, 1, 10, 0, 0)
    s1 = save_signal(db, "RELIANCE", "1h", "ema_rsi_volume", "BUY", ts)
    s2 = save_signal(db, "TCS", "1h", "ema_rsi_volume", "BUY", ts)
    assert s1 is not None
    assert s2 is not None


def test_different_timeframes_allowed(db):
    ts = datetime(2024, 6, 1, 10, 0, 0)
    s1 = save_signal(db, "RELIANCE", "1h", "ema_rsi_volume", "BUY", ts)
    s2 = save_signal(db, "RELIANCE", "1d", "ema_rsi_volume", "BUY", ts)
    assert s1 is not None
    assert s2 is not None


def test_get_latest_signal(db):
    save_signal(db, "INFY", "1d", "ema_rsi_volume", "HOLD", datetime(2024, 6, 1, 0, 0, 0))
    save_signal(db, "INFY", "1d", "ema_rsi_volume", "BUY", datetime(2024, 6, 2, 0, 0, 0))
    latest = get_latest_signal(db, "INFY", "1d")
    assert latest is not None
    assert latest.signal_type == "BUY"
    assert latest.candle_timestamp == datetime(2024, 6, 2, 0, 0, 0)


def test_get_recent_signals_filter(db):
    save_signal(db, "TCS", "1h", "ema_rsi_volume", "BUY", datetime(2024, 6, 1, 9, 0, 0))
    save_signal(db, "TCS", "1h", "ema_rsi_volume", "HOLD", datetime(2024, 6, 1, 10, 0, 0))
    save_signal(db, "INFY", "1h", "ema_rsi_volume", "BUY", datetime(2024, 6, 1, 9, 0, 0))

    tcs_only = get_recent_signals(db, symbol="TCS")
    assert len(tcs_only) == 2

    buy_only = get_recent_signals(db, signal_type="BUY")
    assert all(s.signal_type == "BUY" for s in buy_only)


# ---------- scheduler_service unit tests ----------

def test_run_cycle_returns_summary(db):
    """run_cycle should complete without raising and return a summary dict."""
    from app.services.scheduler_service import run_cycle
    from app.utils.candle_validator import ValidationResult
    from app.schemas.candle import CandleCreate

    # Mock fetch so we don't hit yfinance
    def mock_fetch(symbol, timeframe, period=None):
        from datetime import timedelta
        base = datetime(2024, 1, 1, 9, 0, 0)
        candles = [
            CandleCreate(
                symbol=symbol, timeframe=timeframe,
                timestamp_utc=base + timedelta(hours=i),
                open=100.0 + i * 0.1, high=110.0 + i * 0.1,
                low=90.0 + i * 0.1, close=105.0 + i * 0.1, volume=50000.0,
            )
            for i in range(80)
        ]
        result = ValidationResult(valid=candles, rejected=0, reasons={})
        return candles, result

    with patch("app.services.scheduler_service.fetch_candles", side_effect=mock_fetch):
        summary = run_cycle(db)

    assert "symbols_processed" in summary
    assert "candles_inserted" in summary
    assert "signals_generated" in summary
    assert summary["errors"] == 0


def test_run_cycle_is_idempotent(db):
    """Running the cycle twice should not create duplicate signals."""
    from app.services.scheduler_service import run_cycle
    from app.utils.candle_validator import ValidationResult
    from app.schemas.candle import CandleCreate

    def mock_fetch(symbol, timeframe, period=None):
        from datetime import timedelta
        base = datetime(2024, 1, 1, 9, 0, 0)
        candles = [
            CandleCreate(
                symbol=symbol, timeframe=timeframe,
                timestamp_utc=base + timedelta(hours=i),
                open=100.0 + i * 0.1, high=110.0 + i * 0.1,
                low=90.0 + i * 0.1, close=105.0 + i * 0.1, volume=50000.0,
            )
            for i in range(80)
        ]
        result = ValidationResult(valid=candles, rejected=0, reasons={})
        return candles, result

    with patch("app.services.scheduler_service.fetch_candles", side_effect=mock_fetch):
        first = run_cycle(db)
        second = run_cycle(db)

    # Second run should generate no new signals (all duplicates)
    assert second["signals_generated"] == 0
    assert second["signals_skipped_duplicate"] > 0


# ---------- API endpoint tests ----------

def test_list_signals_empty(client):
    response = client.get("/api/v1/signals")
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["data"] == []


def test_get_signal_fallback_no_candles(client):
    """When no candles and no persisted signal, returns HOLD with a helpful message."""
    response = client.get("/api/v1/signals/RELIANCE/1h")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["signal_type"] == "HOLD"
    assert data["data"]["persisted"] is False


def test_scheduler_run_once(client):
    """POST /scheduler/run-once triggers a cycle and returns a summary."""
    from app.utils.candle_validator import ValidationResult

    def mock_fetch(symbol, timeframe, period=None):
        return [], ValidationResult(valid=[], rejected=0, reasons={})

    with patch("app.services.scheduler_service.fetch_candles", side_effect=mock_fetch):
        response = client.post("/api/v1/scheduler/run-once")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "symbols_processed" in data["data"]


def test_scheduler_status(client):
    response = client.get("/api/v1/scheduler/status")
    assert response.status_code == 200
    assert "running" in response.json()["data"]
