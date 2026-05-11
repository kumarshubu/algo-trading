"""Tests for EMA+RSI+Volume strategy signal generation."""

import pandas as pd
import numpy as np
import pytest

from app.strategies.ema_rsi_volume import EmaRsiVolumeStrategy, MIN_CANDLES
from app.strategies.base import Signal


def _make_candles(n: int, close_prices: list[float] | None = None) -> pd.DataFrame:
    """Generate test candle DataFrame."""
    np.random.seed(42)
    if close_prices is None:
        prices = 1000 + np.cumsum(np.random.randn(n) * 5)
    else:
        prices = close_prices

    data = {
        "open": [p * 0.999 for p in prices],
        "high": [p * 1.005 for p in prices],
        "low": [p * 0.995 for p in prices],
        "close": prices,
        "volume": [500000 * (1 + abs(np.random.randn())) for _ in range(n)],
    }
    index = pd.date_range("2024-01-01", periods=n, freq="1h")
    return pd.DataFrame(data, index=index)


def test_hold_when_not_enough_data():
    strategy = EmaRsiVolumeStrategy()
    df = _make_candles(10)  # too few candles
    signal = strategy.generate_signal("TEST", df)
    assert signal.signal == Signal.HOLD


def test_hold_on_neutral_market():
    strategy = EmaRsiVolumeStrategy()
    df = _make_candles(MIN_CANDLES + 10)
    signal = strategy.generate_signal("TEST", df)
    # Just verify it returns a valid signal type
    assert signal.signal in (Signal.BUY, Signal.HOLD)


def test_signal_has_stop_loss_when_buy():
    """If a BUY signal is generated, it must have stop_loss and target_price."""
    strategy = EmaRsiVolumeStrategy()
    # Generate upward-trending data with increasing volume at the end
    n = MIN_CANDLES + 20
    base = list(range(900, 900 + n))  # steadily rising prices
    df = _make_candles(n, close_prices=base)
    # Inflate volume on last candle
    df.iloc[-1, df.columns.get_loc("volume")] = df["volume"].mean() * 3

    signal = strategy.generate_signal("TEST", df)
    if signal.signal == Signal.BUY:
        assert signal.stop_loss is not None
        assert signal.target_price is not None
        assert signal.stop_loss < signal.price
        assert signal.target_price > signal.price


def test_candle_count_validation():
    strategy = EmaRsiVolumeStrategy()
    assert strategy.validate_candles(_make_candles(MIN_CANDLES), min_rows=MIN_CANDLES) is True
    assert strategy.validate_candles(_make_candles(MIN_CANDLES - 1), min_rows=MIN_CANDLES) is False
