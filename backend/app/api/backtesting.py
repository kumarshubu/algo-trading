"""
Backtesting API endpoints.
Runs backtests on stored candle data using available strategies.
"""

from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import pandas as pd

from app.db.database import get_db
from app.services.candle_service import get_candles
from app.strategies.ema_rsi_volume import EmaRsiVolumeStrategy
from app.backtesting.engine import BacktestEngine

router = APIRouter(prefix="/backtest", tags=["backtesting"])

STRATEGY_REGISTRY = {
    "ema_rsi_volume": EmaRsiVolumeStrategy,
}


@router.post("/run")
def run_backtest(
    symbol: str,
    timeframe: Literal["15m", "1h", "1d"],
    strategy_name: str = "ema_rsi_volume",
    initial_balance: float = 100000.0,
    db: Session = Depends(get_db),
):
    """
    Run a backtest on stored candle data.
    Fetches candles from DB and runs the specified strategy walk-forward.
    """
    symbol = symbol.upper().strip()

    if strategy_name not in STRATEGY_REGISTRY:
        raise HTTPException(status_code=400, detail=f"Unknown strategy: {strategy_name}")

    candles = get_candles(db, symbol=symbol, timeframe=timeframe, limit=1000)
    if len(candles) < 60:
        raise HTTPException(
            status_code=400,
            detail=f"Not enough candle data for {symbol}/{timeframe}. "
                   f"Use /candles/{symbol}/{timeframe}/fetch to load data first.",
        )

    # Build DataFrame for strategy - oldest first
    df = pd.DataFrame(
        [
            {
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
            }
            for c in candles
        ],
        index=pd.DatetimeIndex([c.timestamp_utc for c in candles]),
    )

    strategy_class = STRATEGY_REGISTRY[strategy_name]
    strategy = strategy_class()
    engine = BacktestEngine(strategy=strategy, initial_balance=initial_balance)
    result = engine.run(symbol, df)

    return {"success": True, "data": result.summary()}
