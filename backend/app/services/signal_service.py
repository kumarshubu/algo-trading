"""
Signal persistence service.
Saves strategy signals to the database with idempotency guarantees.
The same candle can never produce duplicate signals.
"""

import json
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models.signal import Signal
from app.core.logging import get_logger

logger = get_logger(__name__)


def save_signal(
    db: Session,
    symbol: str,
    timeframe: str,
    strategy_name: str,
    signal_type: str,
    candle_timestamp: datetime,
    metadata: Optional[dict] = None,
) -> Optional[Signal]:
    """
    Persist a signal. Returns None if the signal already exists (idempotent).
    The unique constraint on (symbol, timeframe, strategy_name, candle_timestamp)
    ensures the same candle never produces duplicate signals.
    """
    db_signal = Signal(
        symbol=symbol,
        timeframe=timeframe,
        strategy_name=strategy_name,
        signal_type=signal_type,
        candle_timestamp=candle_timestamp,
        generated_at=datetime.now(timezone.utc).replace(tzinfo=None),
        metadata_json=json.dumps(metadata) if metadata else None,
    )
    try:
        db.add(db_signal)
        db.commit()
        db.refresh(db_signal)
        logger.info(
            "signal_saved",
            symbol=symbol,
            timeframe=timeframe,
            signal_type=signal_type,
            candle_ts=str(candle_timestamp),
        )
        return db_signal
    except IntegrityError:
        db.rollback()
        logger.debug(
            "signal_duplicate_skipped",
            symbol=symbol,
            timeframe=timeframe,
            strategy=strategy_name,
            candle_ts=str(candle_timestamp),
        )
        return None


def get_latest_signal(
    db: Session,
    symbol: str,
    timeframe: str,
    strategy_name: str = "ema_rsi_volume",
) -> Optional[Signal]:
    return (
        db.query(Signal)
        .filter(
            Signal.symbol == symbol,
            Signal.timeframe == timeframe,
            Signal.strategy_name == strategy_name,
        )
        .order_by(Signal.candle_timestamp.desc())
        .first()
    )


def get_recent_signals(
    db: Session,
    symbol: Optional[str] = None,
    timeframe: Optional[str] = None,
    signal_type: Optional[str] = None,
    limit: int = 50,
) -> list[Signal]:
    query = db.query(Signal)
    if symbol:
        query = query.filter(Signal.symbol == symbol.upper())
    if timeframe:
        query = query.filter(Signal.timeframe == timeframe)
    if signal_type:
        query = query.filter(Signal.signal_type == signal_type.upper())
    return query.order_by(Signal.generated_at.desc()).limit(min(limit, 500)).all()
