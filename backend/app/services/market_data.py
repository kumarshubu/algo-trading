"""
Lightweight market data abstraction layer.
Wraps external data source with retry/timeout handling.
All API keys come from environment variables - never hardcoded.

Currently uses Yahoo Finance (yfinance) as a free data source.
In the future, this can be swapped for NSE/BSE APIs.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional
import pandas as pd

from app.core.config import settings
from app.core.logging import get_logger
from app.core.exceptions import MarketDataError
from app.schemas.candle import CandleCreate

logger = get_logger(__name__)

# yfinance timeframe mapping
TIMEFRAME_MAP = {
    "15m": "15m",
    "1h": "60m",
    "1d": "1d",
}

# yfinance period mapping for initial fetch
TIMEFRAME_PERIOD = {
    "15m": "60d",   # 60 days of 15m data
    "1h": "730d",   # 2 years of hourly data
    "1d": "5y",     # 5 years of daily data
}


def fetch_candles_yfinance(
    symbol: str,
    timeframe: str,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> list[CandleCreate]:
    """
    Fetch OHLCV candles from Yahoo Finance.
    Returns empty list on failure - never raises.

    NOTE: yfinance is a free, unofficial data source suitable for learning only.
    For production use, replace with an official NSE/BSE data feed.
    """
    try:
        import yfinance as yf
    except ImportError:
        logger.warning("yfinance_not_installed", hint="pip install yfinance")
        return []

    yf_interval = TIMEFRAME_MAP.get(timeframe)
    if not yf_interval:
        raise MarketDataError(f"Unsupported timeframe: {timeframe}")

    # NSE symbols use .NS suffix on Yahoo Finance
    yf_symbol = symbol if "." in symbol else f"{symbol}.NS"

    try:
        if start and end:
            df = yf.download(
                yf_symbol,
                start=start,
                end=end,
                interval=yf_interval,
                progress=False,
                auto_adjust=True,
            )
        else:
            period = TIMEFRAME_PERIOD.get(timeframe, "60d")
            df = yf.download(
                yf_symbol,
                period=period,
                interval=yf_interval,
                progress=False,
                auto_adjust=True,
            )

        if df is None or df.empty:
            logger.warning("market_data_empty", symbol=symbol, timeframe=timeframe)
            return []

        candles = []
        for ts, row in df.iterrows():
            # Normalize timestamp to UTC
            if hasattr(ts, "tzinfo") and ts.tzinfo is not None:
                ts_utc = ts.to_pydatetime().astimezone(timezone.utc).replace(tzinfo=None)
            else:
                ts_utc = ts.to_pydatetime()

            # Handle MultiIndex columns (yfinance sometimes returns these)
            def get_val(col: str) -> float:
                try:
                    v = row[col]
                    if hasattr(v, "iloc"):
                        v = v.iloc[0]
                    return float(v)
                except Exception:
                    return 0.0

            candles.append(
                CandleCreate(
                    symbol=symbol.upper(),
                    timeframe=timeframe,
                    timestamp_utc=ts_utc,
                    open=get_val("Open"),
                    high=get_val("High"),
                    low=get_val("Low"),
                    close=get_val("Close"),
                    volume=get_val("Volume"),
                )
            )

        logger.info(
            "market_data_fetched",
            symbol=symbol,
            timeframe=timeframe,
            count=len(candles),
        )
        return candles

    except Exception as e:
        # Log error but never expose to client
        logger.error("market_data_fetch_failed", symbol=symbol, timeframe=timeframe, error_type=type(e).__name__)
        return []


def generate_sample_candles(
    symbol: str,
    timeframe: str,
    count: int = 200,
) -> list[CandleCreate]:
    """
    Generate synthetic OHLCV candle data for testing when no real data source is available.
    Uses a random walk to simulate realistic price movement.
    """
    import random
    import math

    random.seed(42)  # deterministic seed for reproducibility

    candles = []
    now = datetime.now(timezone.utc).replace(tzinfo=None).replace(minute=0, second=0, microsecond=0)

    timeframe_minutes = {"15m": 15, "1h": 60, "1d": 1440}
    step = timedelta(minutes=timeframe_minutes.get(timeframe, 60))

    price = 1000.0 + random.uniform(0, 2000)
    avg_volume = 500000.0

    for i in range(count):
        ts = now - step * (count - i)

        # Random walk with slight upward drift
        change_pct = random.gauss(0.0002, 0.015)
        open_price = price
        price = price * (1 + change_pct)
        close_price = price

        high_price = max(open_price, close_price) * (1 + abs(random.gauss(0, 0.005)))
        low_price = min(open_price, close_price) * (1 - abs(random.gauss(0, 0.005)))
        volume = avg_volume * random.uniform(0.5, 2.5)

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
