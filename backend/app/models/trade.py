"""
SQLAlchemy model for paper trades.
PAPER TRADING ONLY - NO REAL EXECUTION

Trade status values:
  OPEN        - position is open
  CLOSED      - manually closed
  STOPPED     - stop loss triggered
  TARGET_HIT  - target price reached
"""

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Float, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class PaperTrade(Base):
    __tablename__ = "paper_trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(4), nullable=False)  # BUY or SELL
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    exit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    pnl: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    strategy_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN")
    stop_loss: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Links this trade back to the signal that triggered it (nullable for manual trades)
    signal_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        nullable=False,
    )
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<PaperTrade {self.symbol} {self.side} @ {self.entry_price} [{self.status}]>"
