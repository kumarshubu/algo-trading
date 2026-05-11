"""SQLAlchemy model for persisted strategy signals."""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, DateTime, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False)
    strategy_name: Mapped[str] = mapped_column(String(100), nullable=False)
    signal_type: Mapped[str] = mapped_column(String(10), nullable=False)  # BUY, SELL, HOLD
    candle_timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Idempotency: same candle can only produce one signal per symbol/timeframe/strategy
    __table_args__ = (
        UniqueConstraint(
            "symbol", "timeframe", "strategy_name", "candle_timestamp",
            name="uq_signal_symbol_tf_strategy_ts",
        ),
    )

    def __repr__(self) -> str:
        return f"<Signal {self.symbol} {self.timeframe} {self.signal_type} @ {self.candle_timestamp}>"
