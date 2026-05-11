"""Tests for candle validation rules."""

from datetime import datetime, timezone, timedelta
from app.utils.candle_validator import validate_candles, is_valid_candle
from app.schemas.candle import CandleCreate


def _candle(**kwargs) -> CandleCreate:
    base = dict(
        symbol="TEST",
        timeframe="1h",
        timestamp_utc=datetime(2024, 6, 1, 10, 0, 0),
        open=100.0,
        high=110.0,
        low=90.0,
        close=105.0,
        volume=50000.0,
    )
    base.update(kwargs)
    return CandleCreate(**base)


def test_valid_candle_passes():
    assert is_valid_candle(_candle()) is True


def test_zero_open_rejected():
    assert is_valid_candle(_candle(open=0.0)) is False


def test_negative_close_rejected():
    assert is_valid_candle(_candle(close=-1.0)) is False


def test_negative_volume_rejected():
    assert is_valid_candle(_candle(volume=-100.0)) is False


def test_zero_volume_allowed():
    # Zero volume is valid (e.g. holiday half-session)
    assert is_valid_candle(_candle(volume=0.0)) is True


def test_future_timestamp_rejected():
    future = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1)
    assert is_valid_candle(_candle(timestamp_utc=future)) is False


def test_high_below_open_rejected():
    assert is_valid_candle(_candle(open=100.0, high=90.0, low=85.0, close=95.0)) is False


def test_high_below_close_rejected():
    assert is_valid_candle(_candle(open=100.0, high=104.0, low=90.0, close=106.0)) is False


def test_low_above_open_rejected():
    assert is_valid_candle(_candle(open=100.0, high=110.0, low=105.0, close=108.0)) is False


def test_low_above_close_rejected():
    assert is_valid_candle(_candle(open=100.0, high=110.0, low=107.0, close=105.0)) is False


def test_validate_candles_filters_invalid():
    candles = [
        _candle(timestamp_utc=datetime(2024, 6, 1, 9, 0, 0)),   # valid
        _candle(timestamp_utc=datetime(2024, 6, 1, 10, 0, 0), volume=-1),  # invalid
        _candle(timestamp_utc=datetime(2024, 6, 1, 11, 0, 0)),  # valid
    ]
    result = validate_candles(candles, symbol="TEST")
    assert len(result.valid) == 2
    assert result.rejected == 1
    assert "negative_volume" in result.reasons


def test_validate_candles_all_valid():
    candles = [
        _candle(timestamp_utc=datetime(2024, 6, 1, h, 0, 0)) for h in range(5)
    ]
    result = validate_candles(candles, symbol="TEST")
    assert len(result.valid) == 5
    assert result.rejected == 0


def test_validate_empty_list():
    result = validate_candles([], symbol="TEST")
    assert result.valid == []
    assert result.rejected == 0
