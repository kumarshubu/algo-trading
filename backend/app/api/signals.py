"""
Signals API endpoints.

GET /api/v1/signals                   — list recent persisted signals
GET /api/v1/signals/{symbol}/{tf}     — latest signal (persisted → fallback to live)
"""

import json
import re
from typing import Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
import pandas as pd

_SYMBOL_RE = re.compile(r'^[A-Z0-9&-]{1,20}$')

from app.db.database import get_db
from app.schemas.signal import SignalRead, LiveSignalRead
from app.schemas.common import SuccessResponse
from app.services.signal_service import get_recent_signals, get_latest_signal
from app.services.candle_service import get_candles
from app.strategies.ema_rsi_volume import EmaRsiVolumeStrategy

router = APIRouter(prefix="/signals", tags=["signals"])

_strategy = EmaRsiVolumeStrategy()


@router.get("", response_model=SuccessResponse[list[SignalRead]])
def list_signals(
    symbol: Optional[str] = Query(default=None),
    timeframe: Optional[str] = Query(default=None),
    signal_type: Optional[str] = Query(default=None, description="BUY, SELL, or HOLD"),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """List recent persisted signals, newest first."""
    if symbol is not None:
        symbol = symbol.upper().strip()
        if not _SYMBOL_RE.match(symbol):
            raise HTTPException(status_code=400, detail="Invalid symbol")
    signals = get_recent_signals(
        db,
        symbol=symbol,
        timeframe=timeframe,
        signal_type=signal_type,
        limit=limit,
    )
    return SuccessResponse(data=[SignalRead.model_validate(s) for s in signals])


@router.get("/{symbol}/{timeframe}", response_model=SuccessResponse[LiveSignalRead])
def get_signal(
    symbol: str,
    timeframe: Literal["15m", "1h", "1d"],
    strategy_name: str = Query(default="ema_rsi_volume"),
    db: Session = Depends(get_db),
):
    """
    Return the latest signal for a symbol/timeframe.
    Checks the persisted signals DB first (set by the scheduler).
    Falls back to computing live from stored candles if no persisted signal exists.
    """
    symbol = symbol.upper().strip()
    if not _SYMBOL_RE.match(symbol):
        raise HTTPException(status_code=400, detail="Invalid symbol")

    # Try persisted signal first
    persisted = get_latest_signal(db, symbol, timeframe, strategy_name)
    if persisted:
        try:
            meta = json.loads(persisted.metadata_json) if persisted.metadata_json else {}
        except (json.JSONDecodeError, TypeError):
            meta = {}
        return SuccessResponse(
            data=LiveSignalRead(
                symbol=symbol,
                timeframe=timeframe,
                strategy_name=persisted.strategy_name,
                signal_type=persisted.signal_type,
                price=meta.get("price", 0.0),
                stop_loss=meta.get("stop_loss"),
                target_price=meta.get("target_price"),
                reason=meta.get("reason", ""),
                persisted=True,
                generated_at=persisted.generated_at,
            )
        )

    # Fallback: compute live from stored candles
    candles = get_candles(db, symbol=symbol, timeframe=timeframe, limit=200)
    if not candles:
        return SuccessResponse(
            data=LiveSignalRead(
                symbol=symbol,
                timeframe=timeframe,
                strategy_name=strategy_name,
                signal_type="HOLD",
                price=0.0,
                reason="No candle data — use Load Data to fetch candles first.",
                persisted=False,
            )
        )

    df = pd.DataFrame(
        [{"open": c.open, "high": c.high, "low": c.low, "close": c.close, "volume": c.volume}
         for c in candles],
        index=pd.DatetimeIndex([c.timestamp_utc for c in candles]),
    )
    trade_signal = _strategy.generate_signal(symbol, df)

    return SuccessResponse(
        data=LiveSignalRead(
            symbol=symbol,
            timeframe=timeframe,
            strategy_name=strategy_name,
            signal_type=trade_signal.signal.value,
            price=trade_signal.price,
            stop_loss=trade_signal.stop_loss,
            target_price=trade_signal.target_price,
            reason=trade_signal.reason,
            persisted=False,
        )
    )
