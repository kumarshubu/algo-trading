"""Pydantic schemas for watchlist."""

from datetime import datetime
from pydantic import BaseModel, field_validator


class WatchlistItemCreate(BaseModel):
    symbol: str

    @field_validator("symbol")
    @classmethod
    def symbol_uppercase(cls, v: str) -> str:
        return v.upper().strip()


class WatchlistItemRead(BaseModel):
    id: int
    symbol: str
    created_at: datetime

    model_config = {"from_attributes": True}
