"""Pydantic schemas for paper portfolio and positions."""

from datetime import datetime
from pydantic import BaseModel


class PaperPositionRead(BaseModel):
    id: int
    symbol: str
    quantity: float
    average_price: float
    unrealized_pnl: float
    updated_at: datetime

    model_config = {"from_attributes": True}


class PortfolioSummary(BaseModel):
    virtual_balance: float
    initial_balance: float
    total_realized_pnl: float
    daily_loss: float
    open_positions_count: int
    total_unrealized_pnl: float
    portfolio_value: float  # balance + unrealized pnl
