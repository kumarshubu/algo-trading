"""
Pending execution service.
PAPER TRADING ONLY - NO REAL EXECUTION.

Implements the realistic next-candle execution flow:

  1. BUY signal generated at candle T close
  2. PendingExecution created with execute_after_timestamp = candle T
  3. On next scheduler cycle, candle T+1 exists
  4. Trade executed at candle T+1 OPEN (+ slippage)
  5. PendingExecution marked EXECUTED

This prevents the unrealistic "execute at signal candle close" pattern.
"""

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

import math
from app.core.config import settings
from app.core.logging import get_logger
from app.core.exceptions import (
    InsufficientBalanceError,
    MaxPositionsError,
    MaxDailyLossError,
    StrategyKillSwitchError,
)
from app.models.pending_execution import PendingExecution
from app.models.signal import Signal
from app.models.position import PaperPosition
from app.schemas.trade import SimulateOrderRequest
from app.services.paper_trading import (
    simulate_order,
    get_or_create_portfolio,
    _apply_slippage,
)
from app.services.candle_service import get_next_candle

logger = get_logger(__name__)

# PAPER TRADING ONLY - NO REAL EXECUTION
PAPER_TRADING_ONLY = True


def create_pending_execution(db: Session, signal: Signal) -> Optional[PendingExecution]:
    """
    Create a pending execution for a BUY signal.
    Returns None if one already exists for this signal (idempotent).
    """
    if signal.signal_type != "BUY":
        return None

    pending = PendingExecution(
        signal_id=signal.id,
        symbol=signal.symbol,
        timeframe=signal.timeframe,
        strategy_name=signal.strategy_name,
        execute_after_timestamp=signal.candle_timestamp,
        status="PENDING",
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    try:
        db.add(pending)
        db.commit()
        db.refresh(pending)
        logger.info(
            "pending_execution_created",
            symbol=signal.symbol,
            timeframe=signal.timeframe,
            execute_after=str(signal.candle_timestamp),
            pending_id=pending.id,
        )
        return pending
    except IntegrityError:
        db.rollback()
        logger.debug(
            "pending_execution_duplicate_skipped",
            signal_id=signal.id,
            symbol=signal.symbol,
        )
        return None


def process_pending_executions(db: Session) -> dict:
    """
    Process all PENDING executions that have a next candle available.
    Executes each at the next candle's OPEN price.
    Returns a summary dict.
    """
    pending_list = (
        db.query(PendingExecution)
        .filter(PendingExecution.status == "PENDING")
        .order_by(PendingExecution.created_at.asc())
        .all()
    )

    summary = {"checked": len(pending_list), "executed": 0, "skipped": 0, "cancelled": 0}

    for pending in pending_list:
        try:
            result = _process_one_pending(db, pending)
            if result == "EXECUTED":
                summary["executed"] += 1
            elif result == "SKIPPED":
                summary["skipped"] += 1
            elif result == "CANCELLED":
                summary["cancelled"] += 1
        except Exception as e:
            # Never crash — log and continue
            logger.error(
                "pending_execution_error",
                pending_id=pending.id,
                symbol=pending.symbol,
                error_type=type(e).__name__,
            )
            summary["skipped"] += 1

    if summary["executed"] > 0 or summary["cancelled"] > 0:
        logger.info("pending_executions_processed", **summary)

    return summary


def _process_one_pending(db: Session, pending: PendingExecution) -> str:
    """
    Try to execute one pending trade.
    Returns "EXECUTED", "SKIPPED" (next candle not yet available), or "CANCELLED".
    """
    # Find the next candle that opened AFTER the signal candle
    next_candle = get_next_candle(
        db,
        symbol=pending.symbol,
        timeframe=pending.timeframe,
        after_ts=pending.execute_after_timestamp,
    )

    if not next_candle:
        # Next candle hasn't arrived yet — try again next cycle
        logger.debug(
            "pending_execution_waiting",
            pending_id=pending.id,
            symbol=pending.symbol,
            timeframe=pending.timeframe,
            waiting_for_candle_after=str(pending.execute_after_timestamp),
        )
        return "SKIPPED"

    # Use the next candle's OPEN as execution price (+ slippage applied in simulate_order)
    entry_price = next_candle.open

    logger.info(
        "pending_execution_next_candle_found",
        pending_id=pending.id,
        symbol=pending.symbol,
        signal_candle=str(pending.execute_after_timestamp),
        next_candle=str(next_candle.timestamp_utc),
        entry_price=entry_price,
    )

    # Duplicate position check — never open two positions for the same symbol
    existing = db.query(PaperPosition).filter(PaperPosition.symbol == pending.symbol).first()
    if existing:
        return _cancel(db, pending, "open_position_exists")

    # Position sizing (same as before, accounting for slippage + brokerage)
    portfolio = get_or_create_portfolio(db)
    trade_value = portfolio.virtual_balance * settings.max_capital_per_trade_pct
    cost_per_unit = entry_price * (1 + settings.slippage_pct) * (1 + settings.brokerage_pct)
    # math.floor guarantees we never exceed trade_value budget (round can exceed by 1 ULP)
    quantity = math.floor(trade_value / cost_per_unit * 10_000) / 10_000
    if quantity <= 0:
        return _cancel(db, pending, "quantity_zero")

    # Load stop_loss / target from the originating signal's metadata
    stop_loss, target_price = _load_signal_meta(db, pending.signal_id)

    request = SimulateOrderRequest(
        symbol=pending.symbol,
        side="BUY",
        quantity=quantity,
        price=entry_price,
        strategy_name=pending.strategy_name,
        stop_loss=stop_loss,
        target_price=target_price,
    )

    try:
        trade = simulate_order(db, request)
        trade.signal_id = pending.signal_id
        db.commit()
    except (InsufficientBalanceError, MaxPositionsError, MaxDailyLossError) as e:
        return _cancel(db, pending, f"risk_check: {e.message}")
    except StrategyKillSwitchError as e:
        return _cancel(db, pending, "strategy_disabled")

    # Mark as executed
    pending.status = "EXECUTED"
    db.commit()

    logger.info(
        "pending_execution_executed",
        pending_id=pending.id,
        symbol=pending.symbol,
        entry_price=entry_price,
        next_candle_open=next_candle.open,
        next_candle_ts=str(next_candle.timestamp_utc),
        trade_id=trade.id,
    )
    return "EXECUTED"


def _cancel(db: Session, pending: PendingExecution, reason: str) -> str:
    pending.status = "CANCELLED"
    pending.cancel_reason = reason
    db.commit()
    logger.info(
        "pending_execution_cancelled",
        pending_id=pending.id,
        symbol=pending.symbol,
        reason=reason,
    )
    return "CANCELLED"


def _load_signal_meta(db: Session, signal_id: int) -> tuple[Optional[float], Optional[float]]:
    """Load stop_loss and target_price from the signal's metadata JSON."""
    import json
    signal = db.query(Signal).filter(Signal.id == signal_id).first()
    if not signal or not signal.metadata_json:
        return None, None
    try:
        meta = json.loads(signal.metadata_json)
        return meta.get("stop_loss"), meta.get("target_price")
    except (json.JSONDecodeError, AttributeError):
        return None, None


def get_pending_executions(
    db: Session,
    status: Optional[str] = None,
    symbol: Optional[str] = None,
    limit: int = 50,
) -> list[PendingExecution]:
    query = db.query(PendingExecution)
    if status:
        query = query.filter(PendingExecution.status == status.upper())
    if symbol:
        query = query.filter(PendingExecution.symbol == symbol.upper())
    return query.order_by(PendingExecution.created_at.desc()).limit(min(limit, 200)).all()


def cancel_pending_execution(db: Session, pending_id: int) -> bool:
    pending = db.query(PendingExecution).filter(PendingExecution.id == pending_id).first()
    if not pending or pending.status != "PENDING":
        return False
    _cancel(db, pending, "manually_cancelled")
    return True
