"""
EMA + RSI + Volume strategy.
PAPER TRADING ONLY - NO REAL EXECUTION.

BUY when:
  - EMA20 > EMA50 (uptrend)
  - RSI > 60 (momentum)
  - Volume > 1.5x 20-period average volume

SELL when:
  - Stop loss hit (configurable %)
  - Target hit (configurable %)

Indicators implemented directly with pandas — no extra dependencies needed.
"""

import pandas as pd

from app.strategies.base import BaseStrategy, Signal, TradeSignal
from app.core.logging import get_logger

logger = get_logger(__name__)

EMA_FAST = 20
EMA_SLOW = 50
RSI_PERIOD = 14
RSI_BUY_THRESHOLD = 60
VOLUME_MULTIPLIER = 1.5
VOLUME_AVG_PERIOD = 20
STOP_LOSS_PCT = 0.03    # 3% stop loss
TARGET_PCT = 0.06       # 6% target (2:1 risk-reward)
MIN_CANDLES = EMA_SLOW + RSI_PERIOD + 5


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _rsi(series: pd.Series, period: int) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, float("nan"))
    return 100 - (100 / (1 + rs))


class EmaRsiVolumeStrategy(BaseStrategy):
    """
    Simple trend-following strategy using EMA crossover, RSI momentum,
    and volume confirmation.
    """

    name = "ema_rsi_volume"

    def generate_signal(self, symbol: str, candles: pd.DataFrame) -> TradeSignal:
        if not self.validate_candles(candles, min_rows=MIN_CANDLES):
            return TradeSignal(signal=Signal.HOLD, symbol=symbol, price=0.0, reason="Not enough data")

        df = candles.copy()
        df["ema20"] = _ema(df["close"], EMA_FAST)
        df["ema50"] = _ema(df["close"], EMA_SLOW)
        df["rsi"] = _rsi(df["close"], RSI_PERIOD)
        df["vol_avg"] = df["volume"].rolling(window=VOLUME_AVG_PERIOD).mean()

        # Use only the last completed candle — no lookahead
        last = df.iloc[-1]

        if pd.isna(last["ema20"]) or pd.isna(last["ema50"]) or pd.isna(last["rsi"]) or pd.isna(last["vol_avg"]):
            return TradeSignal(signal=Signal.HOLD, symbol=symbol, price=last["close"], reason="Indicator not ready")

        price = float(last["close"])
        ema20 = float(last["ema20"])
        ema50 = float(last["ema50"])
        rsi = float(last["rsi"])
        volume = float(last["volume"])
        vol_avg = float(last["vol_avg"])

        trend_up = ema20 > ema50
        rsi_strong = rsi > RSI_BUY_THRESHOLD
        vol_high = volume > vol_avg * VOLUME_MULTIPLIER

        if trend_up and rsi_strong and vol_high:
            stop_loss = round(price * (1 - STOP_LOSS_PCT), 2)
            target = round(price * (1 + TARGET_PCT), 2)

            logger.info(
                "strategy_signal_buy",
                symbol=symbol,
                price=price,
                ema20=round(ema20, 2),
                ema50=round(ema50, 2),
                rsi=round(rsi, 2),
                volume=volume,
                vol_avg=round(vol_avg, 2),
            )
            return TradeSignal(
                signal=Signal.BUY,
                symbol=symbol,
                price=price,
                stop_loss=stop_loss,
                target_price=target,
                reason=f"EMA20({ema20:.2f}) > EMA50({ema50:.2f}), RSI={rsi:.1f}, Vol={volume:.0f} > 1.5x avg",
            )

        logger.debug(
            "strategy_signal_hold",
            symbol=symbol,
            trend_up=trend_up,
            rsi_strong=rsi_strong,
            vol_high=vol_high,
        )
        return TradeSignal(
            signal=Signal.HOLD,
            symbol=symbol,
            price=price,
            reason="Conditions not met",
        )
