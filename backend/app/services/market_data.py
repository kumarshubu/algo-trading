"""
Sample candle generator for offline / test use.

The real yfinance-based fetcher lives in market_data_service.py.
This module is intentionally kept narrow: only the deterministic
synthetic data generator belongs here.
"""

import random
from datetime import datetime, timezone, timedelta

from app.schemas.candle import CandleCreate


def generate_sample_candles(
    symbol: str,
    timeframe: str,
    count: int = 200,
) -> list[CandleCreate]:
    """
    Generate synthetic OHLCV candle data for testing when no real data is available.
    Uses a random walk to simulate realistic price movement.

    Uses a local Random instance seeded with 42 so output is deterministic without
    mutating the global random state (which was a hidden side-effect in the old code).
    """
    rng = random.Random(42)  # isolated instance — does not affect global random state

    candles: list[CandleCreate] = []
    now = datetime.now(timezone.utc).replace(tzinfo=None).replace(minute=0, second=0, microsecond=0)

    timeframe_minutes = {"15m": 15, "1h": 60, "1d": 1440}
    step = timedelta(minutes=timeframe_minutes.get(timeframe, 60))

    price = 1000.0 + rng.uniform(0, 2000)
    avg_volume = 500_000.0

    for i in range(count):
        ts = now - step * (count - i)

        change_pct = rng.gauss(0.0002, 0.015)
        open_price = price
        price = price * (1 + change_pct)
        close_price = price

        high_price = max(open_price, close_price) * (1 + abs(rng.gauss(0, 0.005)))
        low_price = min(open_price, close_price) * (1 - abs(rng.gauss(0, 0.005)))
        volume = avg_volume * rng.uniform(0.5, 2.5)

        candles.append(
            CandleCreate(
                symbol=symbol.upper(),
                timeframe=timeframe,
                timestamp_utc=ts,
                open=round(open_price, 2),
                high=round(high_price, 2),
                low=round(low_price, 2),
                close=round(close_price, 2),
                volume=round(volume, 0),
            )
        )

    return candles
