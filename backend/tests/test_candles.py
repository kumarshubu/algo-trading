"""Tests for candle storage service."""

from datetime import datetime
from app.services.candle_service import upsert_candle, get_candles, get_candle_count
from app.schemas.candle import CandleCreate


def _make_candle(symbol="TEST", timeframe="1h", offset_hours=0):
    return CandleCreate(
        symbol=symbol,
        timeframe=timeframe,
        timestamp_utc=datetime(2024, 1, 1, offset_hours, 0, 0),
        open=100.0,
        high=105.0,
        low=95.0,
        close=102.0,
        volume=10000.0,
    )


def test_insert_candle(db):
    candle = _make_candle()
    result = upsert_candle(db, candle)
    assert result is not None
    assert result.symbol == "TEST"
    assert result.timeframe == "1h"


def test_duplicate_candle_skipped(db):
    candle = _make_candle()
    first = upsert_candle(db, candle)
    second = upsert_candle(db, candle)  # same timestamp - should be skipped
    assert first is not None
    assert second is None  # duplicate


def test_get_candles_returns_ordered(db):
    for i in range(5):
        upsert_candle(db, _make_candle(offset_hours=i))

    candles = get_candles(db, symbol="TEST", timeframe="1h")
    assert len(candles) == 5
    # Verify ascending order
    for i in range(1, len(candles)):
        assert candles[i].timestamp_utc > candles[i - 1].timestamp_utc


def test_candle_count(db):
    for i in range(3):
        upsert_candle(db, _make_candle(offset_hours=i))
    assert get_candle_count(db, "TEST", "1h") == 3
