"""Pydantic schemas for persisted signals."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class SignalRead(BaseModel):
    id: int
    symbol: str
    timeframe: str
    strategy_name: str
    signal_type: str
    candle_timestamp: datetime
    generated_at: datetime
    metadata_json: Optional[str] = None

    model_config = {"from_attributes": True}


class LiveSignalRead(BaseModel):
    """On-the-fly signal (not persisted) — used for immediate queries."""
    symbol: str
    timeframe: str
    strategy_name: str
    signal_type: str
    price: float
    stop_loss: Optional[float] = None
    target_price: Optional[float] = None
    reason: str
    persisted: bool = False  # True when returned from DB
    generated_at: Optional[datetime] = None
