"""
Paper trade execution API.
PAPER TRADING ONLY - NO REAL EXECUTION.

Endpoints:
  POST /paper-trades/execute/{signal_id}  — manually execute a signal as a paper trade
  POST /paper-trades/close/{position_id}  — manually close an open position
  GET  /paper-trades                      — list all trades
  GET  /paper-positions                   — list open positions
  GET  /portfolio                         — portfolio summary + equity curve
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.trade import PaperTradeRead, ClosePositionRequest
from app.schemas.portfolio import PaperPositionRead, PortfolioSummary
from app.schemas.common import SuccessResponse
from app.models.trade import PaperTrade
from app.models.position import PaperPosition
from app.services.execution_service import (
    execute_signal,
    get_equity_curve,
)
from app.services.paper_trading import (
    get_or_create_portfolio,
    simulate_close_position,
)
from app.core.logging import get_logger

router = APIRouter(tags=["paper-trades"])
logger = get_logger(__name__)


@router.post("/paper-trades/execute/{signal_id}")
def execute_paper_trade(signal_id: int, db: Session = Depends(get_db)):
    """
    Manually execute a persisted BUY signal as a paper trade.
    PAPER TRADING ONLY - NO REAL EXECUTION.

    The entry price is the latest candle close + slippage (simulates next-candle open).
    Risk checks run automatically (max capital, max positions, daily loss limit).
    """
    result = execute_signal(db, signal_id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])

    return SuccessResponse(data=PaperTradeRead.model_validate(result["trade"]))


@router.post("/paper-trades/close/{position_id}")
def close_paper_position(
    position_id: int,
    request: ClosePositionRequest,
    db: Session = Depends(get_db),
):
    """
    Manually close an open paper position.
    PAPER TRADING ONLY - NO REAL EXECUTION.
    """
    position = db.query(PaperPosition).filter(PaperPosition.id == position_id).first()
    if not position:
        raise HTTPException(status_code=404, detail=f"Position {position_id} not found")

    trade = simulate_close_position(db, position.symbol, request.price, close_status="CLOSED")
    if not trade:
        raise HTTPException(status_code=404, detail=f"No open trade found for {position.symbol}")

    return SuccessResponse(data=PaperTradeRead.model_validate(trade))


@router.get("/paper-trades", response_model=SuccessResponse[list[PaperTradeRead]])
def list_trades(
    symbol: str | None = None,
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """List paper trades, newest first."""
    query = db.query(PaperTrade)
    if symbol:
        query = query.filter(PaperTrade.symbol == symbol.upper())
    if status:
        query = query.filter(PaperTrade.status == status.upper())
    trades = query.order_by(PaperTrade.created_at.desc()).limit(limit).all()
    return SuccessResponse(data=[PaperTradeRead.model_validate(t) for t in trades])


@router.get("/paper-positions", response_model=SuccessResponse[list[PaperPositionRead]])
def list_positions(db: Session = Depends(get_db)):
    """List all open paper positions."""
    positions = db.query(PaperPosition).all()
    return SuccessResponse(data=[PaperPositionRead.model_validate(p) for p in positions])


@router.get("/portfolio", response_model=SuccessResponse[PortfolioSummary])
def portfolio_summary(db: Session = Depends(get_db)):
    """Portfolio summary with equity curve snapshots."""
    portfolio = get_or_create_portfolio(db)
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


@router.get("/portfolio/equity-curve")
def equity_curve(
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """Return historical equity snapshots for plotting the P&L curve."""
    snapshots = get_equity_curve(db, limit=limit)
    return {
        "success": True,
        "data": [
            {
                "timestamp": s.timestamp.isoformat(),
                "balance": s.balance,
                "unrealized_pnl": s.unrealized_pnl,
                "realized_pnl": s.realized_pnl,
                "drawdown_pct": round(s.drawdown * 100, 2),
            }
            for s in snapshots
        ],
    }
