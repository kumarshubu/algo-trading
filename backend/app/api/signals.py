"""
Strategy signal endpoint.
Run a strategy against stored candle data and return the current signal.
"""

from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import pandas as pd

from app.db.database import get_db
from app.services.candle_service import get_candles
from app.strategies.ema_rsi_volume import EmaRsiVolumeStrategy

router = APIRouter(prefix="/signals", tags=["signals"])

STRATEGY_REGISTRY = {
    "ema_rsi_volume": EmaRsiVolumeStrategy,
}


@router.get("/{symbol}/{timeframe}")
def get_signal(
    symbol: str,
    timeframe: Literal["15m", "1h", "1d"],
    strategy_name: str = "ema_rsi_volume",
    db: Session = Depends(get_db),
):
    """Run a strategy on the latest stored candle data and return the current signal."""
    symbol = symbol.upper().strip()

    if strategy_name not in STRATEGY_REGISTRY:
        raise HTTPException(status_code=400, detail=f"Unknown strategy: {strategy_name}")

    candles = get_candles(db, symbol=symbol, timeframe=timeframe, limit=200)
    if not candles:
        raise HTTPException(
            status_code=404,
            detail=f"No candle data found for {symbol}/{timeframe}",
        )

    df = pd.DataFrame(
        [{"open": c.open, "high": c.high, "low": c.low, "close": c.close, "volume": c.volume}
         for c in candles],
        index=pd.DatetimeIndex([c.timestamp_utc for c in candles]),
    )

    strategy_class = STRATEGY_REGISTRY[strategy_name]
    strategy = strategy_class()
    signal = strategy.generate_signal(symbol, df)

    return {
        "success": True,
        "data": {
            "symbol": symbol,
            "timeframe": timeframe,
            "strategy": strategy_name,
            "signal": signal.signal.value,
            "price": signal.price,
            "stop_loss": signal.stop_loss,
            "target_price": signal.target_price,
            "reason": signal.reason,
        },
    }
