"""
Candle storage service.
Handles storing, retrieving, and deduplication of OHLCV candle data.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models.candle import Candle
from app.schemas.candle import CandleCreate
from app.core.logging import get_logger

logger = get_logger(__name__)


def upsert_candle(db: Session, candle: CandleCreate) -> Optional[Candle]:
    """
    Insert a candle, skipping if it already exists (deduplication).
    Returns the saved candle or None if it was a duplicate.
    """
    db_candle = Candle(
        symbol=candle.symbol,
        timeframe=candle.timeframe,
        timestamp_utc=candle.timestamp_utc,
        open=candle.open,
        high=candle.high,
        low=candle.low,
        close=candle.close,
        volume=candle.volume,
    )
    try:
        db.add(db_candle)
        db.commit()
        db.refresh(db_candle)
        return db_candle
    except IntegrityError:
        db.rollback()
        logger.debug(
            "candle_duplicate_skipped",
            symbol=candle.symbol,
            timeframe=candle.timeframe,
            timestamp=str(candle.timestamp_utc),
        )
        return None


def bulk_upsert_candles(db: Session, candles: list[CandleCreate]) -> int:
    """
    Insert multiple candles, skipping duplicates, in a single transaction.

    Uses SQLAlchemy nested transactions (SAVEPOINTs) so each candle's
    conflict is isolated without rolling back the entire batch.
    This replaces the previous pattern of one commit per row, which was
    O(N) in transaction overhead for typical 300-candle initial loads.

    Returns count of newly inserted candles.
    """
    if not candles:
        return 0

    inserted = 0
    for candle in candles:
        try:
            with db.begin_nested():          # SAVEPOINT per candle
                db.add(Candle(
                    symbol=candle.symbol,
                    timeframe=candle.timeframe,
                    timestamp_utc=candle.timestamp_utc,
                    open=candle.open,
                    high=candle.high,
                    low=candle.low,
                    close=candle.close,
                    volume=candle.volume,
                ))
                db.flush()                   # detect constraint violation now
            inserted += 1
        except IntegrityError:
            pass                             # duplicate — savepoint auto-rolled back

    db.commit()                              # single commit for the whole batch
    logger.info("candles_bulk_inserted", count=inserted, skipped=len(candles) - inserted)
    return inserted


def get_candles(
    db: Session,
    symbol: str,
    timeframe: str,
    limit: int = 200,
    from_dt: Optional[datetime] = None,
) -> list[Candle]:
    """Fetch candles ordered by timestamp ascending."""
    query = (
        db.query(Candle)
        .filter(Candle.symbol == symbol, Candle.timeframe == timeframe)
    )
    if from_dt:
        query = query.filter(Candle.timestamp_utc >= from_dt)
    return (
        query.order_by(Candle.timestamp_utc.asc())
        .limit(limit)
        .all()
    )


def get_latest_candle(db: Session, symbol: str, timeframe: str) -> Optional[Candle]:
    """Get the most recent candle for a symbol/timeframe."""
    return (
        db.query(Candle)
        .filter(Candle.symbol == symbol, Candle.timeframe == timeframe)
        .order_by(Candle.timestamp_utc.desc())
        .first()
    )


def get_next_candle(db: Session, symbol: str, timeframe: str, after_ts: datetime) -> Optional[Candle]:
    """Return the first candle that opened AFTER after_ts (used for next-candle execution)."""
    return (
        db.query(Candle)
        .filter(
            Candle.symbol == symbol,
            Candle.timeframe == timeframe,
            Candle.timestamp_utc > after_ts,
        )
        .order_by(Candle.timestamp_utc.asc())
        .first()
    )


def get_candle_count(db: Session, symbol: str, timeframe: str) -> int:
    return (
        db.query(Candle)
        .filter(Candle.symbol == symbol, Candle.timeframe == timeframe)
        .count()
    )
