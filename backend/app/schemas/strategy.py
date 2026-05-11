"""Pydantic schemas for strategies."""

from datetime import datetime
from pydantic import BaseModel


class StrategyRead(BaseModel):
    id: int
    name: str
    enabled: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class StrategyToggleRequest(BaseModel):
    enabled: bool
