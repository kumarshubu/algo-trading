"""
Paper trading engine.
PAPER TRADING ONLY - NO REAL EXECUTION.

Simulates order execution, position management, and PnL calculation
using a virtual balance in INR. All trades are simulated.
"""

from datetime import datetime, timezone, date
from typing import Optional
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

_IST = ZoneInfo("Asia/Kolkata")

from app.core.config import settings
from app.core.exceptions import (
    InsufficientBalanceError,
    MaxPositionsError,
    MaxDailyLossError,
    StrategyKillSwitchError,
    DuplicateSignalTradeError,
)
from app.core.logging import get_logger
from app.models.trade import PaperTrade
from app.models.position import PaperPosition
from app.models.portfolio import PaperPortfolio
from app.models.strategy import Strategy
from app.schemas.trade import SimulateOrderRequest

logger = get_logger(__name__)

# PAPER TRADING ONLY - NO REAL EXECUTION
PAPER_TRADING_ONLY = True


def get_or_create_portfolio(db: Session) -> PaperPortfolio:
    """Load portfolio state from DB, or initialize it fresh."""
    portfolio = db.query(PaperPortfolio).filter(PaperPortfolio.id == 1).first()
    if not portfolio:
        portfolio = PaperPortfolio(
            id=1,
            virtual_balance=settings.initial_virtual_balance_inr,
            initial_balance=settings.initial_virtual_balance_inr,
            total_realized_pnl=0.0,
            daily_loss=0.0,
            daily_loss_reset_date=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        db.add(portfolio)
        db.commit()
        db.refresh(portfolio)
        logger.info("portfolio_initialized", balance=portfolio.virtual_balance)
    return portfolio


def _reset_daily_loss_if_needed(portfolio: PaperPortfolio, db: Session) -> None:
    """Reset daily loss counter when a new IST trading day starts."""
    today = datetime.now(_IST).date()
    reset_date = (
        portfolio.daily_loss_reset_date.replace(tzinfo=timezone.utc).astimezone(_IST).date()
        if portfolio.daily_loss_reset_date else None
    )
    if reset_date != today:
        portfolio.daily_loss = 0.0
        portfolio.daily_loss_reset_date = datetime.now(timezone.utc).replace(tzinfo=None)
        db.commit()


def _apply_slippage(price: float, side: str) -> float:
    """Simulate fixed-percentage slippage on execution price."""
    if side == "BUY":
        return price * (1 + settings.slippage_pct)
    return price * (1 - settings.slippage_pct)


def _calculate_brokerage(trade_value: float) -> float:
    """Simulate brokerage cost."""
    return trade_value * settings.brokerage_pct


def simulate_order(
    db: Session,
    request: SimulateOrderRequest,
    signal_id: Optional[int] = None,
) -> PaperTrade:
    """
    Simulate a paper trade order.
    PAPER TRADING ONLY - NO REAL EXECUTION.

    signal_id: when provided (scheduler path), set on the trade atomically in the
    same commit so crash-recovery can detect duplicate executions via the
    uq_paper_trades_signal_id partial index.
    """
    # Check strategy kill switch
    strategy = db.query(Strategy).filter(Strategy.name == request.strategy_name).first()
    if strategy and not strategy.enabled:
        raise StrategyKillSwitchError(f"Strategy '{request.strategy_name}' is disabled")

    portfolio = get_or_create_portfolio(db)
    _reset_daily_loss_if_needed(portfolio, db)

    # Acquire row-level lock on the portfolio row.
    # All BUY/SELL orders serialize through this single lock so the position-count
    # check and balance deduction are atomic within one Postgres transaction.
    portfolio = (
        db.query(PaperPortfolio).filter(PaperPortfolio.id == 1).with_for_update().first()
    )

    # Daily loss risk check — re-read from the locked row
    max_daily_loss = portfolio.initial_balance * settings.max_daily_loss_pct
    if portfolio.daily_loss >= max_daily_loss:
        raise MaxDailyLossError(
            f"Daily loss limit of ₹{max_daily_loss:.2f} reached. Trading paused for today."
        )

    # Apply simulated slippage
    exec_price = _apply_slippage(request.price, request.side)
    trade_value = exec_price * request.quantity
    brokerage = _calculate_brokerage(trade_value)
    total_cost = trade_value + brokerage

    if request.side == "BUY":
        # Check max capital per trade
        max_capital = portfolio.virtual_balance * settings.max_capital_per_trade_pct
        if total_cost > max_capital:
            raise InsufficientBalanceError(
                f"Trade cost ₹{total_cost:.2f} exceeds max capital per trade ₹{max_capital:.2f}"
            )

        # Check sufficient balance
        if portfolio.virtual_balance < total_cost:
            raise InsufficientBalanceError(
                f"Insufficient virtual balance: ₹{portfolio.virtual_balance:.2f} < ₹{total_cost:.2f}"
            )

        # Position checks INSIDE the portfolio lock — reads committed state,
        # serialized through the FOR UPDATE on portfolio row.
        open_positions = db.query(PaperPosition).count()
        existing = db.query(PaperPosition).filter(PaperPosition.symbol == request.symbol).first()

        if not existing and open_positions >= settings.max_simultaneous_positions:
            raise MaxPositionsError()

        # Deduct from virtual balance
        portfolio.virtual_balance -= total_cost
        portfolio.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

        # Upsert position (averaging is intentional for manual multi-fill trades)
        if existing:
            total_qty = existing.quantity + request.quantity
            existing.average_price = (
                (existing.quantity * existing.average_price + request.quantity * exec_price) / total_qty
            )
            existing.quantity = total_qty
            existing.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        else:
            position = PaperPosition(
                symbol=request.symbol,
                quantity=request.quantity,
                average_price=exec_price,
                unrealized_pnl=0.0,
            )
            db.add(position)

    else:  # SELL
        position = db.query(PaperPosition).filter(PaperPosition.symbol == request.symbol).first()

        proceeds = trade_value - brokerage
        portfolio.virtual_balance += proceeds
        portfolio.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

        if position:
            if request.quantity >= position.quantity:
                db.delete(position)
            else:
                position.quantity -= request.quantity
                position.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

    # Record the trade — signal_id is set here atomically so the
    # uq_paper_trades_signal_id partial index can enforce crash-recovery idempotency.
    trade = PaperTrade(
        symbol=request.symbol,
        side=request.side,
        entry_price=exec_price,
        quantity=request.quantity,
        strategy_name=request.strategy_name,
        status="OPEN" if request.side == "BUY" else "CLOSED",
        stop_loss=request.stop_loss,
        target_price=request.target_price,
        signal_id=signal_id,
    )
    db.add(trade)

    try:
        db.commit()
        db.refresh(trade)
    except IntegrityError as exc:
        db.rollback()
        if signal_id is not None and "uq_paper_trades_signal_id" in str(exc).lower():
            raise DuplicateSignalTradeError(signal_id) from exc
        raise

    logger.info(
        "paper_order_simulated",
        symbol=request.symbol,
        side=request.side,
        price=exec_price,
        quantity=request.quantity,
        strategy=request.strategy_name,
        signal_id=signal_id,
    )
    return trade


def simulate_close_position(
    db: Session,
    symbol: str,
    current_price: float,
    close_status: str = "CLOSED",
) -> Optional[PaperTrade]:
    """
    Close an open paper position at the given price.
    PAPER TRADING ONLY - NO REAL EXECUTION.

    close_status: CLOSED (manual), STOPPED (stop loss), TARGET_HIT (target reached)
    """
    position = db.query(PaperPosition).filter(PaperPosition.symbol == symbol).first()
    if not position:
        return None

    exec_price = _apply_slippage(current_price, "SELL")
    trade_value = exec_price * position.quantity
    brokerage = _calculate_brokerage(trade_value)
    proceeds = trade_value - brokerage

    cost_basis = position.average_price * position.quantity
    pnl = proceeds - cost_basis

    portfolio = get_or_create_portfolio(db)
    portfolio.virtual_balance += proceeds
    portfolio.total_realized_pnl += pnl
    if pnl < 0:
        portfolio.daily_loss += abs(pnl)
    portfolio.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

    # Close ALL open trades for this symbol.
    # Averaging up/down creates multiple OPEN trade records for one position;
    # closing only the latest one (the old .first() behaviour) left earlier trades
    # permanently stuck in OPEN status.  PnL is distributed proportionally by qty.
    open_trades = (
        db.query(PaperTrade)
        .filter(PaperTrade.symbol == symbol, PaperTrade.status == "OPEN")
        .order_by(PaperTrade.created_at.asc())
        .all()
    )

    total_open_qty = sum(t.quantity for t in open_trades)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    last_closed: Optional[PaperTrade] = None

    for trade in open_trades:
        trade.status = close_status
        trade.exit_price = exec_price
        trade.closed_at = now
        trade.pnl = round(pnl * (trade.quantity / total_open_qty), 2) if total_open_qty else 0.0
        last_closed = trade

    db.delete(position)
    db.commit()

    logger.info(
        "paper_position_closed",
        symbol=symbol,
        exit_price=exec_price,
        pnl=round(pnl, 2),
        status=close_status,
        trades_closed=len(open_trades),
    )
    return last_closed


def update_unrealized_pnl(db: Session, symbol: str, current_price: float) -> None:
    """Recalculate unrealized PnL for an open position."""
    position = (
        db.query(PaperPosition)
        .filter(PaperPosition.symbol == symbol)
        .with_for_update()
        .first()
    )
    if not position:
        return
    position.unrealized_pnl = (current_price - position.average_price) * position.quantity
    position.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()


def simulate_pnl(entry_price: float, current_price: float, quantity: float, side: str = "BUY") -> float:
    """Calculate PnL for a simulated position. PAPER TRADING ONLY."""
    if side == "BUY":
        return (current_price - entry_price) * quantity
    return (entry_price - current_price) * quantity


def check_stop_loss_and_target(
    db: Session,
    symbol: str,
    current_price: float,
) -> Optional[str]:
    """
    Check if any open trade's stop loss or target is hit.
    Returns 'STOP_LOSS', 'TARGET', or None.
    PAPER TRADING ONLY - NO REAL EXECUTION.
    """
    open_trade = (
        db.query(PaperTrade)
        .filter(PaperTrade.symbol == symbol, PaperTrade.status == "OPEN")
        .order_by(PaperTrade.created_at.desc())
        .first()
    )
    if not open_trade:
        return None

    if open_trade.stop_loss and current_price <= open_trade.stop_loss:
        simulate_close_position(db, symbol, current_price, close_status="STOPPED")
        logger.info("stop_loss_triggered", symbol=symbol, price=current_price, stop=open_trade.stop_loss)
        return "STOP_LOSS"

    if open_trade.target_price and current_price >= open_trade.target_price:
        simulate_close_position(db, symbol, current_price, close_status="TARGET_HIT")
        logger.info("target_hit", symbol=symbol, price=current_price, target=open_trade.target_price)
        return "TARGET"

    return None
