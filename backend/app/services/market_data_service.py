"""
Real historical market data service using yfinance.
NOTE: yfinance is an unofficial free source — for learning/paper trading only.

Fetches NSE historical OHLCV candles, converts to UTC, and validates them
before they reach the database.
"""

from datetime import datetime, timezone
from typing import Optional

import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.core.logging import get_logger
from app.schemas.candle import CandleCreate
from app.utils.candle_validator import validate_candles, ValidationResult

logger = get_logger(__name__)

# Supported NSE symbols → Yahoo Finance ticker suffix
NSE_SYMBOLS = {
    "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK",
    "WIPRO", "HINDUNILVR", "BAJFINANCE", "SBIN", "ADANIENT",
}

# yfinance interval strings
_YF_INTERVAL = {
    "15m": "15m",
    "1h":  "1h",
    "1d":  "1d",
}

# How far back to fetch on first load
_FETCH_PERIOD = {
    "15m": "60d",    # yfinance limit for intraday
    "1h":  "2y",
    "1d":  "5y",
}


def to_yf_symbol(symbol: str) -> str:
    """Append .NS suffix for NSE stocks if not already present."""
    symbol = symbol.upper().strip()
    return symbol if symbol.endswith(".NS") or symbol.endswith(".BO") else f"{symbol}.NS"


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
def _download_with_retry(yf_symbol: str, interval: str, period: str) -> pd.DataFrame:
    """Download candles from yfinance with retry on failure."""
    import yfinance as yf

    ticker = yf.Ticker(yf_symbol)
    df = ticker.history(period=period, interval=interval, auto_adjust=True, timeout=15)
    return df


def fetch_candles(
    symbol: str,
    timeframe: str,
    period: Optional[str] = None,
) -> tuple[list[CandleCreate], ValidationResult]:
    """
    Fetch and validate historical candles from Yahoo Finance.

    Returns (raw_candles, validation_result) where validation_result.valid
    contains only candles that passed all checks.

    Never raises — returns empty lists on failure.
    """
    if timeframe not in _YF_INTERVAL:
        logger.error("unsupported_timeframe", timeframe=timeframe)
        empty = validate_candles([], symbol)
        return [], empty

    yf_symbol = to_yf_symbol(symbol)
    interval = _YF_INTERVAL[timeframe]
    fetch_period = period or _FETCH_PERIOD[timeframe]

    try:
        df = _download_with_retry(yf_symbol, interval, fetch_period)
    except Exception as e:
        logger.error(
            "market_data_fetch_failed",
            symbol=symbol,
            yf_symbol=yf_symbol,
            timeframe=timeframe,
            error_type=type(e).__name__,
        )
        empty = validate_candles([], symbol)
        return [], empty

    if df is None or df.empty:
        logger.warning("market_data_empty", symbol=symbol, timeframe=timeframe)
        empty = validate_candles([], symbol)
        return [], empty

    raw = _parse_dataframe(df, symbol, timeframe)

    logger.info(
        "market_data_fetched",
        symbol=symbol,
        timeframe=timeframe,
        raw_count=len(raw),
    )

    result = validate_candles(raw, symbol)

    logger.info(
        "market_data_validated",
        symbol=symbol,
        timeframe=timeframe,
        valid=len(result.valid),
        rejected=result.rejected,
    )

    return raw, result


def _parse_dataframe(df: pd.DataFrame, symbol: str, timeframe: str) -> list[CandleCreate]:
    """
    Convert a yfinance DataFrame to a list of CandleCreate objects.
    Normalises timestamps to naive UTC datetimes.
    yfinance 1.x returns capitalised column names: Open, High, Low, Close, Volume.
    """
    candles: list[CandleCreate] = []

    # Normalise column names to lowercase for safety
    df = df.copy()
    df.columns = [str(c).split()[0].lower() for c in df.columns]

    for ts, row in df.iterrows():
        try:
            ts_utc = _to_utc(ts)

            open_  = _safe_float(row, "open")
            high   = _safe_float(row, "high")
            low    = _safe_float(row, "low")
            close  = _safe_float(row, "close")
            volume = _safe_float(row, "volume")

            if any(v is None for v in (open_, high, low, close, volume)):
                continue

            candles.append(CandleCreate(
                symbol=symbol.upper(),
                timeframe=timeframe,
                timestamp_utc=ts_utc,
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=volume,
            ))
        except Exception as e:
            logger.debug("candle_parse_skipped", error_type=type(e).__name__)
            continue

    return candles


def _to_utc(ts) -> datetime:
    """Convert any pandas Timestamp to a naive UTC datetime."""
    if hasattr(ts, "to_pydatetime"):
        dt = ts.to_pydatetime()
    else:
        dt = ts

    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _safe_float(row: pd.Series, col: str) -> Optional[float]:
    """Extract a float value from a row, returning None on any error."""
    try:
        v = row[col]
        if pd.isna(v):
            return None
        return float(v)
    except (KeyError, TypeError, ValueError):
        return None
