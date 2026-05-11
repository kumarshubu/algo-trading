"""
SQLAlchemy model for paper positions.
PAPER TRADING ONLY - NO REAL EXECUTION
"""

from datetime import datetime, timezone
from sqlalchemy import String, Float, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class PaperPosition(Base):
    __tablename__ = "paper_positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, unique=True, index=True)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    average_price: Mapped[float] = mapped_column(Float, nullable=False)
    unrealized_pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<PaperPosition {self.symbol} qty={self.quantity} avg={self.average_price}>"
