"""SQLAlchemy model for structured execution event log."""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class ExecutionEvent(Base):
    __tablename__ = "execution_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # BUY_EXECUTED, SELL_EXECUTED, STOP_LOSS_TRIGGERED, TARGET_HIT,
    # SCHEDULER_FAILED, STALE_DATA, DUPLICATE_BLOCKED, CRASH_RECOVERED,
    # SCHEDULER_OVERLAP_SKIPPED
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    symbol: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    strategy_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    cycle_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    details_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)

    def __repr__(self) -> str:
        return f"<ExecutionEvent {self.event_type} {self.symbol} @ {self.created_at}>"
