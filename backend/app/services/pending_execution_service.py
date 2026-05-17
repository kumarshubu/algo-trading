"""
Pending execution service.
PAPER TRADING ONLY - NO REAL EXECUTION.

Implements the realistic next-candle execution flow:

  1. BUY signal generated at candle T close
  2. PendingExecution created with execute_after_timestamp = candle T
  3. On next scheduler cycle, candle T+1 exists
  4. Trade executed at candle T+1 OPEN (+ slippage)
  5. PendingExecution marked EXECUTED

Crash-recovery guarantee:
  - signal_id is set on the trade atomically inside simulate_order's commit
  - If the process restarts between simulate_order and marking EXECUTED,
    the recovery check at the top of _process_one_pending detects the existing
    trade by signal_id and marks the pending EXECUTED without re-executing.
"""

import math
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.logging import get_logger
from app.core.exceptions import (
    InsufficientBalanceError,
    MaxPositionsError,
    MaxDailyLossError,
    StrategyKillSwitchError,
    DuplicateSignalTradeError,
)
from app.models.pending_execution import PendingExecution
from app.models.signal import Signal
from app.models.position import PaperPosition
from app.models.trade import PaperTrade
from app.schemas.trade import SimulateOrderRequest
from app.services.paper_trading import (
    simulate_order,
    get_or_create_portfolio,
)
from app.services.candle_service import get_next_candle
from app.services import event_service as ev

logger = get_logger(__name__)

# PAPER TRADING ONLY - NO REAL EXECUTION
PAPER_TRADING_ONLY = True


def create_pending_execution(db: Session, signal: Signal) -> Optional[PendingExecution]:
    """
    Create a pending execution for a BUY or SELL signal.
    Returns None for HOLD signals or if one already exists (idempotent).
    """
    if signal.signal_type not in ("BUY", "SELL"):
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


def process_pending_executions(db: Session, cycle_id: Optional[str] = None) -> dict:
    """
    Process all PENDING executions that have a next candle available.
    cycle_id: UUID string from the calling scheduler cycle (for log correlation).
    """
    pending_list = (
        db.query(PendingExecution)
        .filter(PendingExecution.status == "PENDING")
        .order_by(PendingExecution.created_at.asc())
        .all()
    )

    summary = {"checked": len(pending_list), "executed": 0, "skipped": 0, "cancelled": 0, "duplicate_blocked": 0}

    for pending in pending_list:
        try:
            result = _process_one_pending(db, pending, cycle_id)
            if result == "EXECUTED":
                summary["executed"] += 1
            elif result == "SKIPPED":
                summary["skipped"] += 1
            elif result == "CANCELLED":
                summary["cancelled"] += 1
            elif result == "DUPLICATE_BLOCKED":
                summary["duplicate_blocked"] += 1
        except Exception as e:
            logger.error(
                "pending_execution_error",
                pending_id=pending.id,
                symbol=pending.symbol,
                error_type=type(e).__name__,
                cycle_id=cycle_id,
            )
            summary["skipped"] += 1

    if summary["executed"] > 0 or summary["cancelled"] > 0 or summary["duplicate_blocked"] > 0:
        logger.info("pending_executions_processed", **summary, cycle_id=cycle_id)

    return summary


def _process_one_pending(
    db: Session,
    pending: PendingExecution,
    cycle_id: Optional[str] = None,
) -> str:
    """
    Try to execute one pending trade.
    Returns "EXECUTED", "SKIPPED", "CANCELLED", or "DUPLICATE_BLOCKED".
    """
    # ── Crash-recovery idempotency check ────────────────────────────────────
    # If a previous cycle committed the trade but crashed before marking
    # the pending EXECUTED, detect it here and complete the state update.
    existing_trade = (
        db.query(PaperTrade)
        .filter(PaperTrade.signal_id == pending.signal_id)
        .first()
    )
    if existing_trade:
        pending.status = "EXECUTED"
        db.commit()
        logger.warning(
            "pending_execution_crash_recovered",
            pending_id=pending.id,
            symbol=pending.symbol,
            trade_id=existing_trade.id,
            cycle_id=cycle_id,
        )
        ev.emit(db, ev.CRASH_RECOVERED, symbol=pending.symbol,
                strategy_name=pending.strategy_name, cycle_id=cycle_id,
                details={"pending_id": pending.id, "trade_id": existing_trade.id})
        return "EXECUTED"

    # ── Find the next candle ─────────────────────────────────────────────────
    next_candle = get_next_candle(
        db,
        symbol=pending.symbol,
        timeframe=pending.timeframe,
        after_ts=pending.execute_after_timestamp,
    )

    if not next_candle:
        logger.debug(
            "pending_execution_waiting",
            pending_id=pending.id,
            symbol=pending.symbol,
            timeframe=pending.timeframe,
            waiting_for_candle_after=str(pending.execute_after_timestamp),
        )
        return "SKIPPED"

    exec_price = next_candle.open

    logger.info(
        "pending_execution_next_candle_found",
        pending_id=pending.id,
        symbol=pending.symbol,
        signal_candle=str(pending.execute_after_timestamp),
        next_candle=str(next_candle.timestamp_utc),
        exec_price=exec_price,
        cycle_id=cycle_id,
    )

    # ── Route SELL signals to position close ─────────────────────────────────
    sig = db.query(Signal).filter(Signal.id == pending.signal_id).first()
    if sig and sig.signal_type == "SELL":
        return _execute_sell_pending(db, pending, exec_price, next_candle, cycle_id)

    # ── BUY path ─────────────────────────────────────────────────────────────
    # Duplicate position guard: only one open position per symbol.
    # This check is the application-level guard; the portfolio row lock inside
    # simulate_order provides the DB-level serialization.
    existing_pos = db.query(PaperPosition).filter(PaperPosition.symbol == pending.symbol).first()
    if existing_pos:
        result = _cancel(db, pending, "open_position_exists")
        ev.emit(db, ev.DUPLICATE_BLOCKED, symbol=pending.symbol,
                strategy_name=pending.strategy_name, cycle_id=cycle_id,
                details={"pending_id": pending.id, "reason": "open_position_exists"})
        return result

    # Position sizing
    portfolio = get_or_create_portfolio(db)
    trade_value = portfolio.virtual_balance * settings.max_capital_per_trade_pct
    cost_per_unit = exec_price * (1 + settings.slippage_pct) * (1 + settings.brokerage_pct)
    quantity = math.floor(trade_value / cost_per_unit * 10_000) / 10_000
    if quantity <= 0:
        return _cancel(db, pending, "quantity_zero")

    stop_loss, target_price = _load_signal_meta(db, pending.signal_id)

    request = SimulateOrderRequest(
        symbol=pending.symbol,
        side="BUY",
        quantity=quantity,
        price=exec_price,
        strategy_name=pending.strategy_name,
        stop_loss=stop_loss,
        target_price=target_price,
    )

    try:
        # signal_id passed so it is set atomically on the trade in the same commit.
        trade = simulate_order(db, request, signal_id=pending.signal_id)
    except DuplicateSignalTradeError:
        # The DB unique index fired — the trade already exists (concurrent duplicate).
        # Mark pending EXECUTED and count as blocked.
        pending.status = "EXECUTED"
        db.commit()
        logger.warning(
            "duplicate_trade_blocked_by_db",
            pending_id=pending.id,
            symbol=pending.symbol,
            signal_id=pending.signal_id,
            cycle_id=cycle_id,
        )
        ev.emit(db, ev.DUPLICATE_BLOCKED, symbol=pending.symbol,
                strategy_name=pending.strategy_name, cycle_id=cycle_id,
                details={"pending_id": pending.id, "reason": "db_unique_constraint"})
        return "DUPLICATE_BLOCKED"
    except (InsufficientBalanceError, MaxPositionsError, MaxDailyLossError) as e:
        return _cancel(db, pending, f"risk_check: {e.message}")
    except StrategyKillSwitchError:
        return _cancel(db, pending, "strategy_disabled")

    # Atomically mark the pending EXECUTED in the same logical operation
    pending.status = "EXECUTED"
    db.commit()

    ev.emit(db, ev.BUY_EXECUTED, symbol=pending.symbol,
            strategy_name=pending.strategy_name, cycle_id=cycle_id,
            details={
                "pending_id": pending.id,
                "trade_id": trade.id,
                "entry_price": float(exec_price),
                "quantity": float(quantity),
                "next_candle_ts": str(next_candle.timestamp_utc),
            })

    logger.info(
        "pending_execution_executed",
        pending_id=pending.id,
        symbol=pending.symbol,
        entry_price=exec_price,
        next_candle_ts=str(next_candle.timestamp_utc),
        trade_id=trade.id,
        cycle_id=cycle_id,
    )
    return "EXECUTED"


def _execute_sell_pending(
    db: Session,
    pending: PendingExecution,
    exit_price: float,
    next_candle,
    cycle_id: Optional[str] = None,
) -> str:
    """Close open position at next candle's open price for a SELL signal."""
    from app.services.paper_trading import simulate_close_position

    position = db.query(PaperPosition).filter(PaperPosition.symbol == pending.symbol).first()
    if not position:
        return _cancel(db, pending, "no_open_position")

    simulate_close_position(db, pending.symbol, exit_price, close_status="CLOSED")
    pending.status = "EXECUTED"
    db.commit()

    ev.emit(db, ev.SELL_EXECUTED, symbol=pending.symbol,
            strategy_name=pending.strategy_name, cycle_id=cycle_id,
            details={
                "pending_id": pending.id,
                "exit_price": float(exit_price),
                "next_candle_ts": str(next_candle.timestamp_utc),
            })

    logger.info(
        "pending_sell_executed",
        pending_id=pending.id,
        symbol=pending.symbol,
        exit_price=exit_price,
        next_candle_ts=str(next_candle.timestamp_utc),
        cycle_id=cycle_id,
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
