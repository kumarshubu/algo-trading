"""Pydantic schemas for candle data."""

from datetime import datetime
from typing import Literal
from pydantic import BaseModel, field_validator

VALID_TIMEFRAMES = {"15m", "1h", "1d"}


class CandleBase(BaseModel):
    symbol: str
    timeframe: Literal["15m", "1h", "1d"]
    timestamp_utc: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class CandleCreate(CandleBase):
    @field_validator("symbol")
    @classmethod
    def symbol_uppercase(cls, v: str) -> str:
        return v.upper().strip()


class CandleRead(CandleBase):
    id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class CandleQuery(BaseModel):
    symbol: str
    timeframe: Literal["15m", "1h", "1d"]
    limit: int = 200

    @field_validator("symbol")
    @classmethod
    def symbol_uppercase(cls, v: str) -> str:
        return v.upper().strip()

    @field_validator("limit")
    @classmethod
    def limit_range(cls, v: int) -> int:
        if v < 1 or v > 1000:
            raise ValueError("limit must be between 1 and 1000")
        return v
