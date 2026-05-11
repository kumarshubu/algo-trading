"""Analytics API endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services import analytics_service

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/summary")
def analytics_summary(db: Session = Depends(get_db)):
    """All major portfolio and trade performance metrics."""
    return {"success": True, "data": analytics_service.get_summary(db)}


@router.get("/equity-curve")
def equity_curve(
    limit: int = Query(default=500, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    """Equity curve data points for charting (portfolio value over time)."""
    return {"success": True, "data": analytics_service.get_equity_curve(db, limit)}


@router.get("/drawdown")
def drawdown_curve(
    limit: int = Query(default=500, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    """Drawdown percentage over time (peak-to-trough decline)."""
    return {"success": True, "data": analytics_service.get_drawdown_curve(db, limit)}


@router.get("/symbols")
def symbol_analytics(db: Session = Depends(get_db)):
    """Per-symbol trade performance breakdown."""
    return {"success": True, "data": analytics_service.get_symbol_analytics(db)}


@router.get("/timeframes")
def timeframe_analytics(db: Session = Depends(get_db)):
    """Per-strategy/timeframe trade performance breakdown."""
    return {"success": True, "data": analytics_service.get_timeframe_analytics(db)}


@router.get("/trade-streaks")
def trade_streaks(db: Session = Depends(get_db)):
    """Consecutive win/loss streak analytics."""
    return {"success": True, "data": analytics_service.get_trade_streaks(db)}
