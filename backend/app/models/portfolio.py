"""SQLAlchemy model for paper portfolio state (virtual balance)."""

from datetime import datetime, timezone
from sqlalchemy import Integer, DateTime, Numeric, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base

_MONEY = Numeric(precision=15, scale=4, asdecimal=False)


class PaperPortfolio(Base):
    __tablename__ = "paper_portfolio"
    __table_args__ = (
        CheckConstraint("virtual_balance >= 0", name="ck_portfolio_virtual_balance_non_negative"),
        CheckConstraint("daily_loss >= 0",      name="ck_portfolio_daily_loss_non_negative"),
    )

    # Single row - portfolio is always id=1
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    virtual_balance: Mapped[float] = mapped_column(_MONEY, nullable=False)
    initial_balance: Mapped[float] = mapped_column(_MONEY, nullable=False)
    total_realized_pnl: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0.0)
    daily_loss: Mapped[float] = mapped_column(_MONEY, nullable=False, default=0.0)
    daily_loss_reset_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        nullable=False,
    )
