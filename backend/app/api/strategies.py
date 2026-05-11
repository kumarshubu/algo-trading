"""Strategy management API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.db.database import get_db
from app.models.strategy import Strategy
from app.schemas.strategy import StrategyRead, StrategyToggleRequest
from app.schemas.common import SuccessResponse

router = APIRouter(prefix="/strategies", tags=["strategies"])

AVAILABLE_STRATEGIES = ["ema_rsi_volume"]


def ensure_strategies_registered(db: Session) -> None:
    """
    Idempotently register all known strategies.

    Called once at application startup (lifespan) rather than inside the
    GET handler, so the read endpoint has no write side-effects and the
    race condition where concurrent GET requests could collide on INSERT
    is eliminated entirely.
    """
    for name in AVAILABLE_STRATEGIES:
        existing = db.query(Strategy).filter(Strategy.name == name).first()
        if not existing:
            try:
                db.add(Strategy(name=name, enabled=True))
                db.commit()
            except IntegrityError:
                db.rollback()  # another process registered it first — that's fine


@router.get("", response_model=SuccessResponse[list[StrategyRead]])
def list_strategies(db: Session = Depends(get_db)):
    """List all registered strategies and their enabled status."""
    strategies = db.query(Strategy).all()
    return SuccessResponse(data=[StrategyRead.model_validate(s) for s in strategies])


@router.patch("/{name}/toggle", response_model=SuccessResponse[StrategyRead])
def toggle_strategy(
    name: str,
    request: StrategyToggleRequest,
    db: Session = Depends(get_db),
):
    """Enable or disable a strategy (kill switch)."""
    strategy = db.query(Strategy).filter(Strategy.name == name).first()
    if not strategy:
        raise HTTPException(status_code=404, detail=f"Strategy '{name}' not found")
    strategy.enabled = request.enabled
    db.commit()
    db.refresh(strategy)
    return SuccessResponse(data=StrategyRead.model_validate(strategy))
