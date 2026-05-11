"""Candle data API endpoints."""

from typing import Literal
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.candle import CandleRead
from app.schemas.common import SuccessResponse
from app.services.candle_service import get_candles, bulk_upsert_candles, get_candle_count
from app.services.market_data import generate_sample_candles
from app.services.market_data_service import fetch_candles

router = APIRouter(prefix="/candles", tags=["candles"])


@router.get("/{symbol}/{timeframe}", response_model=SuccessResponse[list[CandleRead]])
def get_symbol_candles(
    symbol: str,
    timeframe: Literal["15m", "1h", "1d"],
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """Return stored candles from SQLite, ordered oldest-first."""
    symbol = symbol.upper().strip()
    candles = get_candles(db, symbol=symbol, timeframe=timeframe, limit=limit)
    return SuccessResponse(data=[CandleRead.model_validate(c) for c in candles])


@router.post("/{symbol}/{timeframe}/fetch")
def fetch_and_store_candles(
    symbol: str,
    timeframe: Literal["15m", "1h", "1d"],
    use_sample: bool = Query(
        default=False,
        description="Use synthetic sample data (no internet required)",
    ),
    db: Session = Depends(get_db),
):
    """
    Fetch candles and store in SQLite.
    - use_sample=false (default): fetch real data from Yahoo Finance
    - use_sample=true: generate synthetic candles for offline testing
    """
    symbol = symbol.upper().strip()

    if use_sample:
        raw = generate_sample_candles(symbol, timeframe, count=300)
        valid = raw
    else:
        raw, result = fetch_candles(symbol, timeframe)
        valid = result.valid

    if not valid:
        return {
            "success": False,
            "error": f"No valid candles obtained for {symbol}/{timeframe}.",
        }

    inserted = bulk_upsert_candles(db, valid)
    total = get_candle_count(db, symbol, timeframe)

    return {
        "success": True,
        "data": {
            "symbol": symbol,
            "timeframe": timeframe,
            "source": "sample" if use_sample else "yfinance",
            "fetched": len(raw),
            "inserted": inserted,
            "total_in_db": total,
        },
    }
