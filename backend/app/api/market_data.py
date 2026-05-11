"""
Market data API endpoints.
Fetch real historical candles from Yahoo Finance and store in SQLite.
"""

from typing import Literal, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services.market_data_service import fetch_candles, NSE_SYMBOLS
from app.services.candle_service import bulk_upsert_candles, get_candle_count
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/market-data", tags=["market-data"])


@router.get("/fetch/{symbol}/{timeframe}")
def fetch_and_store(
    symbol: str,
    timeframe: Literal["15m", "1h", "1d"],
    period: Optional[str] = Query(
        default=None,
        description="yfinance period string: 7d, 60d, 1y, 2y, 5y. Defaults to maximum for the timeframe.",
    ),
    db: Session = Depends(get_db),
):
    """
    Fetch historical candles from Yahoo Finance, validate, and store in SQLite.
    Returns a summary of what was fetched, validated, and inserted.
    """
    symbol = symbol.upper().strip()

    raw_candles, result = fetch_candles(symbol, timeframe, period=period)

    if not raw_candles:
        return {
            "success": False,
            "error": f"No data returned from Yahoo Finance for {symbol}/{timeframe}. "
                     "Check that the symbol is a valid NSE ticker (e.g. RELIANCE, TCS).",
        }

    inserted = bulk_upsert_candles(db, result.valid)
    total = get_candle_count(db, symbol, timeframe)

    return {
        "success": True,
        "data": {
            "symbol": symbol,
            "timeframe": timeframe,
            "fetched": len(raw_candles),
            "valid": len(result.valid),
            "rejected": result.rejected,
            "rejection_reasons": result.reasons,
            "inserted": inserted,
            "duplicates_skipped": len(result.valid) - inserted,
            "total_in_db": total,
        },
    }


@router.get("/symbols")
def list_supported_symbols():
    """Return the list of pre-configured NSE symbols."""
    return {
        "success": True,
        "data": {
            "symbols": sorted(NSE_SYMBOLS),
            "note": "Any valid NSE ticker works — these are just pre-configured defaults.",
        },
    }
