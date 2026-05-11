"""SQLAlchemy model for OHLCV candle data."""

from datetime import datetime, timezone
from sqlalchemy import String, Float, Integer, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class Candle(Base):
    __tablename__ = "candles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False)  # 15m, 1h, 1d
    timestamp_utc: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        nullable=False,
    )

    # Prevent duplicate candles for same symbol+timeframe+timestamp
    __table_args__ = (
        UniqueConstraint("symbol", "timeframe", "timestamp_utc", name="uq_candle_symbol_tf_ts"),
    )

    def __repr__(self) -> str:
        return f"<Candle {self.symbol} {self.timeframe} {self.timestamp_utc}>"
