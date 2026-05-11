"""Strategy management API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.strategy import Strategy
from app.schemas.strategy import StrategyRead, StrategyToggleRequest
from app.schemas.common import SuccessResponse

router = APIRouter(prefix="/strategies", tags=["strategies"])

# Registry of available strategy names
AVAILABLE_STRATEGIES = ["ema_rsi_volume"]


@router.get("", response_model=SuccessResponse[list[StrategyRead]])
def list_strategies(db: Session = Depends(get_db)):
    """List all registered strategies and their enabled status."""
    # Auto-register known strategies if not in DB
    for name in AVAILABLE_STRATEGIES:
        existing = db.query(Strategy).filter(Strategy.name == name).first()
        if not existing:
            db.add(Strategy(name=name, enabled=True))
    db.commit()

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
