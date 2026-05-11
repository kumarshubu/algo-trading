"""Candle data API endpoints."""

from typing import Literal
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.candle import CandleRead, CandleCreate
from app.schemas.common import SuccessResponse
from app.services.candle_service import get_candles, bulk_upsert_candles, get_candle_count
from app.services.market_data import fetch_candles_yfinance, generate_sample_candles

router = APIRouter(prefix="/candles", tags=["candles"])


@router.get("/{symbol}/{timeframe}", response_model=SuccessResponse[list[CandleRead]])
def get_symbol_candles(
    symbol: str,
    timeframe: Literal["15m", "1h", "1d"],
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    symbol = symbol.upper().strip()
    candles = get_candles(db, symbol=symbol, timeframe=timeframe, limit=limit)
    return SuccessResponse(data=[CandleRead.model_validate(c) for c in candles])


@router.post("/{symbol}/{timeframe}/fetch")
def fetch_and_store_candles(
    symbol: str,
    timeframe: Literal["15m", "1h", "1d"],
    use_sample: bool = Query(default=False, description="Use synthetic sample data instead of real API"),
    db: Session = Depends(get_db),
):
    """
    Fetch candles from market data source and store in DB.
    Set use_sample=true to generate synthetic data for testing without an API key.
    """
    symbol = symbol.upper().strip()

    if use_sample:
        candles = generate_sample_candles(symbol, timeframe, count=300)
    else:
        candles = fetch_candles_yfinance(symbol, timeframe)
        if not candles:
            # Fall back to sample data if fetch fails
            candles = generate_sample_candles(symbol, timeframe, count=300)

    inserted = bulk_upsert_candles(db, candles)
    total = get_candle_count(db, symbol, timeframe)

    return {
        "success": True,
        "data": {
            "symbol": symbol,
            "timeframe": timeframe,
            "fetched": len(candles),
            "inserted": inserted,
            "total_in_db": total,
        },
    }
