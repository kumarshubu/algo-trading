"""SQLAlchemy model for scheduler cycle audit log."""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class SchedulerRun(Base):
    __tablename__ = "scheduler_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # RUNNING, COMPLETED, FAILED
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="RUNNING")
    symbols_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    candles_inserted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    signals_generated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pending_executed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    errors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stale_skips: Mapped[int] = mapped_column(Integer, nullable=True, default=0)
    duplicate_blocks: Mapped[int] = mapped_column(Integer, nullable=True, default=0)
    error_detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<SchedulerRun {self.job_id} {self.started_at} [{self.status}]>"
