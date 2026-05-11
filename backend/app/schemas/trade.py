"""
Pydantic schemas for paper trades.
PAPER TRADING ONLY - NO REAL EXECUTION
"""

from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator


class SimulateOrderRequest(BaseModel):
    """Request to simulate a paper trade order. NOT a real order."""
    symbol: str
    side: Literal["BUY", "SELL"]
    quantity: float = Field(gt=0)
    price: float = Field(gt=0)
    strategy_name: str
    stop_loss: Optional[float] = None
    target_price: Optional[float] = None

    @field_validator("symbol")
    @classmethod
    def symbol_uppercase(cls, v: str) -> str:
        return v.upper().strip()

    @field_validator("quantity", "price")
    @classmethod
    def positive_number(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Must be positive")
        return v


class PaperTradeRead(BaseModel):
    id: int
    symbol: str
    side: str
    entry_price: float
    exit_price: Optional[float]
    quantity: float
    pnl: Optional[float]
    strategy_name: str
    status: str  # OPEN, CLOSED, STOPPED, TARGET_HIT
    stop_loss: Optional[float]
    target_price: Optional[float]
    signal_id: Optional[int] = None
    created_at: datetime
    closed_at: Optional[datetime]

    model_config = {"from_attributes": True}


class ClosePositionRequest(BaseModel):
    symbol: str
    price: float = Field(gt=0)

    @field_validator("symbol")
    @classmethod
    def symbol_uppercase(cls, v: str) -> str:
        return v.upper().strip()
