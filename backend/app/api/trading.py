"""
Paper trading API endpoints.
PAPER TRADING ONLY - NO REAL EXECUTION.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.trade import SimulateOrderRequest, PaperTradeRead, ClosePositionRequest
from app.schemas.portfolio import PaperPositionRead, PortfolioSummary
from app.schemas.common import SuccessResponse
from app.services import paper_trading
from app.models.trade import PaperTrade
from app.models.position import PaperPosition

router = APIRouter(prefix="/trading", tags=["paper-trading"])


@router.post("/simulate-order", response_model=SuccessResponse[PaperTradeRead])
def simulate_order(
    request: SimulateOrderRequest,
    db: Session = Depends(get_db),
):
    """Simulate a paper trade order. PAPER TRADING ONLY - NO REAL EXECUTION."""
    trade = paper_trading.simulate_order(db, request)
    return SuccessResponse(data=PaperTradeRead.model_validate(trade))


@router.post("/close-position", response_model=SuccessResponse[PaperTradeRead])
def close_position(
    request: ClosePositionRequest,
    db: Session = Depends(get_db),
):
    """Close an open paper position. PAPER TRADING ONLY - NO REAL EXECUTION."""
    trade = paper_trading.simulate_close_position(db, request.symbol, request.price)
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


@router.post("/reset")
def reset_portfolio(db: Session = Depends(get_db)):
    """
    Reset paper portfolio to initial state.
    Useful for starting a fresh paper trading session.
    """
    from datetime import datetime
    from app.models.portfolio import PaperPortfolio

    db.query(PaperTrade).delete()
    db.query(PaperPosition).delete()
    db.query(PaperPortfolio).delete()
    db.commit()

    portfolio = paper_trading.get_or_create_portfolio(db)
    return {
        "success": True,
        "data": {"message": "Portfolio reset", "balance": portfolio.virtual_balance},
    }
