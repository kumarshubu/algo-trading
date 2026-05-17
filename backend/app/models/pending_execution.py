"""
SQLAlchemy model for pending executions.
PAPER TRADING ONLY - NO REAL EXECUTION.

A BUY or SELL signal creates a PendingExecution immediately.
The scheduler processes it when the next candle is available,
executing the entry/exit at that candle's OPEN price — not the signal candle's close.

Status values:
  PENDING   - waiting for next candle
  EXECUTED  - trade placed
  CANCELLED - skipped (position existed, risk check failed, etc.)
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class PendingExecution(Base):
    __tablename__ = "pending_executions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    signal_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False)
    strategy_name: Mapped[str] = mapped_column(String(100), nullable=False)
    # The candle timestamp that generated the signal.
    # We wait until a candle with timestamp > this exists, then use its open.
    execute_after_timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    cancel_reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # One pending execution per signal — prevents duplicates
    __table_args__ = (
        UniqueConstraint("signal_id", name="uq_pending_execution_signal_id"),
    )

    def __repr__(self) -> str:
        return f"<PendingExecution {self.symbol}/{self.timeframe} [{self.status}]>"
