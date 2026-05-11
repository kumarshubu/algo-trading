"""
Paper trade execution service.
PAPER TRADING ONLY - NO REAL EXECUTION.

Connects persisted signals to the paper trading engine.
Handles risk checks, duplicate prevention, and position lifecycle management.
"""

import json
import math
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.core.exceptions import (
    InsufficientBalanceError,
    MaxPositionsError,
    MaxDailyLossError,
    StrategyKillSwitchError,
)
from app.models.signal import Signal
from app.models.trade import PaperTrade
from app.models.position import PaperPosition
from app.models.equity_snapshot import EquitySnapshot
from app.schemas.trade import SimulateOrderRequest
from app.services.paper_trading import (
    simulate_order,
    simulate_close_position,
    get_or_create_portfolio,
    update_unrealized_pnl,
    check_stop_loss_and_target,
)
from app.services.candle_service import get_latest_candle

logger = get_logger(__name__)

# PAPER TRADING ONLY - NO REAL EXECUTION
PAPER_TRADING_ONLY = True


def execute_signal(db: Session, signal_id: int) -> dict:
    """
    Execute a persisted BUY signal as a paper trade.
    PAPER TRADING ONLY - NO REAL EXECUTION.

    Returns {"success": True/False, "trade": ..., "error": ...}
    """
    signal = db.query(Signal).filter(Signal.id == signal_id).first()
    if not signal:
        return {"success": False, "error": f"Signal {signal_id} not found"}

    return _execute_signal_object(db, signal)


def execute_latest_buy_signal(db: Session, symbol: str, timeframe: str, strategy_name: str) -> dict:
    """
    Execute the latest BUY signal for a symbol/timeframe if no position is open.
    Used by auto-execution mode.
    """
    latest = (
        db.query(Signal)
        .filter(
            Signal.symbol == symbol,
            Signal.timeframe == timeframe,
            Signal.strategy_name == strategy_name,
            Signal.signal_type == "BUY",
        )
        .order_by(Signal.candle_timestamp.desc())
        .first()
    )
    if not latest:
        return {"success": False, "error": "No BUY signal found"}

    return _execute_signal_object(db, latest)


def _execute_signal_object(db: Session, signal: Signal) -> dict:
    """Core execution logic shared by both manual and auto paths."""

    # 1. Only BUY signals open new positions
    if signal.signal_type != "BUY":
        return {
            "success": False,
            "error": f"Signal type is {signal.signal_type} — only BUY signals open positions",
        }

    # 2. Duplicate position prevention: skip if already holding this symbol
    existing = db.query(PaperPosition).filter(PaperPosition.symbol == signal.symbol).first()
    if existing:
        logger.info(
            "execution_duplicate_skipped",
            symbol=signal.symbol,
            reason="open_position_exists",
        )
        return {"success": False, "error": f"Position already open for {signal.symbol}"}

    # 3. Get execution price — latest candle close is the proxy for "next candle open"
    #    The slippage in simulate_order adds realism on top of this.
    latest_candle = get_latest_candle(db, signal.symbol, signal.timeframe)
    if not latest_candle:
        # Try daily if the requested timeframe has no data
        latest_candle = get_latest_candle(db, signal.symbol, "1d")
    if not latest_candle:
        return {"success": False, "error": f"No price data for {signal.symbol}"}

    price = latest_candle.close

    # 4. Position sizing: fixed % of current virtual balance.
    # Divide by estimated total cost per unit (including slippage + brokerage)
    # so the final order cost stays within the max_capital limit.
    portfolio = get_or_create_portfolio(db)
    trade_value = portfolio.virtual_balance * settings.max_capital_per_trade_pct
    cost_per_unit = price * (1 + settings.slippage_pct) * (1 + settings.brokerage_pct)
    quantity = math.floor(trade_value / cost_per_unit * 10_000) / 10_000
    if quantity <= 0:
        return {"success": False, "error": "Calculated quantity is zero"}

    # 5. Pull stop_loss and target from signal metadata
    meta: dict = {}
    if signal.metadata_json:
        try:
            meta = json.loads(signal.metadata_json)
        except json.JSONDecodeError:
            pass

    stop_loss = meta.get("stop_loss")
    target_price = meta.get("target_price")

    # 6. Execute via paper trading engine (risk checks run inside)
    request = SimulateOrderRequest(
        symbol=signal.symbol,
        side="BUY",
        quantity=quantity,
        price=price,
        strategy_name=signal.strategy_name,
        stop_loss=stop_loss,
        target_price=target_price,
    )

    try:
        trade = simulate_order(db, request)
    except (InsufficientBalanceError, MaxPositionsError, MaxDailyLossError) as e:
        logger.warning("execution_risk_check_failed", symbol=signal.symbol, error=e.message)
        return {"success": False, "error": e.message}
    except StrategyKillSwitchError as e:
        logger.warning("execution_strategy_disabled", symbol=signal.symbol)
        return {"success": False, "error": e.message}

    # 7. Link trade back to the signal that triggered it
    trade.signal_id = signal.id
    db.commit()

    logger.info(
        "paper_trade_executed",
        symbol=signal.symbol,
        price=price,
        quantity=quantity,
        signal_id=signal.id,
        trade_id=trade.id,
    )
    return {"success": True, "trade": trade}


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
