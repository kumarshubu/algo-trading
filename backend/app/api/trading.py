"""
Paper trading API endpoints.
PAPER TRADING ONLY - NO REAL EXECUTION.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.db.database import get_db
from app.schemas.trade import PaperTradeRead, ClosePositionRequest
from app.schemas.portfolio import PaperPositionRead, PortfolioSummary
from app.schemas.common import SuccessResponse
from app.services import paper_trading
from app.models.trade import PaperTrade
from app.models.position import PaperPosition
from app.core.logging import get_logger
from sqlalchemy import func

logger = get_logger(__name__)
limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/trading", tags=["paper-trading"])


@router.post("/close-position", response_model=SuccessResponse[PaperTradeRead])
@limiter.limit("30/minute")
def close_position(
    body: ClosePositionRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Close an open paper position. PAPER TRADING ONLY - NO REAL EXECUTION."""
    trade = paper_trading.simulate_close_position(db, body.symbol, body.price)
    if not trade:
        raise HTTPException(status_code=404, detail=f"No open position for {request.symbol}")
    return SuccessResponse(data=PaperTradeRead.model_validate(trade))


@router.get("/positions", response_model=SuccessResponse[list[PaperPositionRead]])
def get_positions(db: Session = Depends(get_db)):
    """Get all open paper positions."""
    positions = db.query(PaperPosition).all()
    return SuccessResponse(data=[PaperPositionRead.model_validate(p) for p in positions])


@router.get("/trades", response_model=SuccessResponse[list[PaperTradeRead]])
def get_trades(
    symbol: str | None = None,
    status: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """Get paper trade history."""
    query = db.query(PaperTrade)
    if symbol:
        query = query.filter(PaperTrade.symbol == symbol.upper())
    if status:
        query = query.filter(PaperTrade.status == status.upper())
    trades = query.order_by(PaperTrade.created_at.desc()).limit(min(limit, 200)).all()
    return SuccessResponse(data=[PaperTradeRead.model_validate(t) for t in trades])


@router.get("/portfolio", response_model=SuccessResponse[PortfolioSummary])
def get_portfolio(db: Session = Depends(get_db)):
    """Get paper portfolio summary."""
    portfolio = paper_trading.get_or_create_portfolio(db)
    positions = db.query(PaperPosition).all()

    total_unrealized_pnl = sum(p.unrealized_pnl for p in positions)
    portfolio_value = portfolio.virtual_balance + total_unrealized_pnl

    return SuccessResponse(
        data=PortfolioSummary(
            virtual_balance=round(portfolio.virtual_balance, 2),
            initial_balance=round(portfolio.initial_balance, 2),
            total_realized_pnl=round(portfolio.total_realized_pnl, 2),
            daily_loss=round(portfolio.daily_loss, 2),
            open_positions_count=len(positions),
            total_unrealized_pnl=round(total_unrealized_pnl, 2),
            portfolio_value=round(portfolio_value, 2),
        )
    )


@router.get("/open-positions/check")
def check_open_positions(db: Session = Depends(get_db)):
    """
    Detect duplicate OPEN trade records for the same symbol.
    Safe: true means no duplicates; the system is consistent.
    """
    # Find symbols that have more than one OPEN trade record
    duplicates_query = (
        db.query(PaperTrade.symbol, func.count(PaperTrade.id).label("open_count"))
        .filter(PaperTrade.status == "OPEN")
        .group_by(PaperTrade.symbol)
        .having(func.count(PaperTrade.id) > 1)
        .all()
    )

    duplicate_symbols = [
        {"symbol": row.symbol, "open_trade_count": row.open_count}
        for row in duplicates_query
    ]

    # Also check for orphaned OPEN trades (trade OPEN but no matching position)
    open_trade_symbols = {
        row.symbol
        for row in db.query(PaperTrade.symbol)
        .filter(PaperTrade.status == "OPEN")
        .distinct()
        .all()
    }
    position_symbols = {
        row.symbol
        for row in db.query(PaperPosition.symbol).all()
    }
    orphaned_trades = sorted(open_trade_symbols - position_symbols)

    return {
        "success": True,
        "data": {
            "duplicate_open_positions": duplicate_symbols,
            "orphaned_open_trades": orphaned_trades,
            "safe": len(duplicate_symbols) == 0 and len(orphaned_trades) == 0,
        },
    }


@router.post("/reset")
@limiter.limit("5/minute")
def reset_portfolio(request: Request, db: Session = Depends(get_db)):
    """
    Reset paper portfolio to initial state.
    Useful for starting a fresh paper trading session.
    """
    from datetime import datetime, timezone
    from app.models.portfolio import PaperPortfolio
    from app.core.config import settings

    db.query(PaperTrade).delete()
    db.query(PaperPosition).delete()
    db.query(PaperPortfolio).delete()
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
    logger.info(
        "portfolio_reset",
        client_ip=request.client.host if request.client else "unknown",
        new_balance=portfolio.virtual_balance,
    )
    return {
        "success": True,
        "data": {"message": "Portfolio reset", "balance": portfolio.virtual_balance},
    }
