"""
Base class for all paper trading strategies.
Strategies only return signals - they never execute real trades.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional
import pandas as pd


class Signal(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class TradeSignal:
    signal: Signal
    symbol: str
    price: float
    stop_loss: Optional[float] = None
    target_price: Optional[float] = None
    reason: str = ""


class BaseStrategy(ABC):
    """
    Abstract base for all strategies.
    generate_signal() receives historical candle data and returns a signal.
    It must ONLY look at data up to the current candle - no lookahead.
    """

    name: str = "base"

    @abstractmethod
    def generate_signal(self, symbol: str, candles: pd.DataFrame) -> TradeSignal:
        """
        Given OHLCV candle data (oldest first), return a trading signal.
        candles columns: open, high, low, close, volume (all lowercase)
        index: timestamp_utc (datetime)
        """
        ...

    def validate_candles(self, candles: pd.DataFrame, min_rows: int) -> bool:
        """Returns True if there's enough data to generate a signal."""
        return candles is not None and len(candles) >= min_rows
