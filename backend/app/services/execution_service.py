"""
Paper trade execution service.
PAPER TRADING ONLY - NO REAL EXECUTION.

Handles position lifecycle: stop/target checks, PnL updates, equity snapshots.
Entry execution is handled exclusively by pending_execution_service (next-candle flow).
"""

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.position import PaperPosition
from app.models.equity_snapshot import EquitySnapshot
from app.services.paper_trading import (
    get_or_create_portfolio,
    update_unrealized_pnl,
    check_stop_loss_and_target,
)
from app.services.candle_service import get_latest_candle

logger = get_logger(__name__)

# PAPER TRADING ONLY - NO REAL EXECUTION
PAPER_TRADING_ONLY = True


def check_and_update_positions(db: Session) -> dict:
    """
    Check all open positions for stop loss / target hits and update unrealized PnL.
    Called by the scheduler every cycle.
    PAPER TRADING ONLY - NO REAL EXECUTION.
    """
    positions = db.query(PaperPosition).all()
    summary = {"checked": 0, "stopped": 0, "target_hit": 0, "pnl_updated": 0}

    for pos in positions:
        # Use best available candle timeframe for current price
        latest = (
            get_latest_candle(db, pos.symbol, "15m")
            or get_latest_candle(db, pos.symbol, "1h")
            or get_latest_candle(db, pos.symbol, "1d")
        )
        if not latest:
            continue

        current_price = latest.close

        # Update unrealized PnL
        update_unrealized_pnl(db, pos.symbol, current_price)
        summary["pnl_updated"] += 1

        # Check stop loss / target — closes position and sets correct status
        result = check_stop_loss_and_target(db, pos.symbol, current_price)
        if result == "STOP_LOSS":
            summary["stopped"] += 1
        elif result == "TARGET":
            summary["target_hit"] += 1

        summary["checked"] += 1

    return summary


def take_equity_snapshot(db: Session) -> EquitySnapshot:
    """Record a point-in-time portfolio snapshot for equity curve tracking."""
    portfolio = get_or_create_portfolio(db)
    positions = db.query(PaperPosition).all()

    unrealized_pnl = sum(p.unrealized_pnl for p in positions)
    portfolio_value = portfolio.virtual_balance + unrealized_pnl

    # Drawdown: how far below peak we are (only tracks downside)
    peak = portfolio.initial_balance + max(portfolio.total_realized_pnl, 0)
    drawdown = max(0.0, (peak - portfolio_value) / peak) if peak > 0 else 0.0

    snapshot = EquitySnapshot(
        timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
        balance=round(portfolio.virtual_balance, 2),
        unrealized_pnl=round(unrealized_pnl, 2),
        realized_pnl=round(portfolio.total_realized_pnl, 2),
        drawdown=round(drawdown, 6),
    )
    db.add(snapshot)
    db.commit()
    return snapshot


def get_equity_curve(db: Session, limit: int = 200) -> list[EquitySnapshot]:
    """Return recent equity snapshots for charting."""
    return (
        db.query(EquitySnapshot)
        .order_by(EquitySnapshot.timestamp.asc())
        .limit(limit)
        .all()
    )
