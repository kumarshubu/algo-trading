"""
Pending execution API endpoints.
PAPER TRADING ONLY - NO REAL EXECUTION.

GET  /pending-executions         — list pending/executed/cancelled records
POST /pending-executions/process — manually process all eligible pending trades
GET  /pending-executions/status  — summary counts by status
POST /pending-executions/{id}/cancel — cancel a specific pending execution
"""

from typing import Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services.pending_execution_service import (
    process_pending_executions,
    get_pending_executions,
    cancel_pending_execution,
)
from app.models.pending_execution import PendingExecution

router = APIRouter(prefix="/pending-executions", tags=["pending-executions"])


class PendingExecutionRead(BaseModel):
    id: int
    signal_id: int
    symbol: str
    timeframe: str
    strategy_name: str
    execute_after_timestamp: str
    status: str
    cancel_reason: Optional[str] = None
    created_at: str

    model_config = {"from_attributes": True}


@router.get("")
def list_pending_executions(
    status: Optional[str] = Query(default=None, description="PENDING, EXECUTED, or CANCELLED"),
    symbol: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """List pending executions, newest first."""
    items = get_pending_executions(db, status=status, symbol=symbol, limit=limit)
    return {
        "success": True,
        "data": [
            {
                "id": p.id,
                "signal_id": p.signal_id,
                "symbol": p.symbol,
                "timeframe": p.timeframe,
                "strategy_name": p.strategy_name,
                "execute_after_timestamp": p.execute_after_timestamp.isoformat(),
                "status": p.status,
                "cancel_reason": p.cancel_reason,
                "created_at": p.created_at.isoformat(),
            }
            for p in items
        ],
    }


@router.post("/process")
def process_pending(db: Session = Depends(get_db)):
    """
    Manually process all PENDING executions that have a next candle available.
    Trades execute at the next candle's OPEN price (+ slippage).
    PAPER TRADING ONLY - NO REAL EXECUTION.
    """
    result = process_pending_executions(db)
    return {"success": True, "data": result}


@router.get("/status")
def pending_execution_status(db: Session = Depends(get_db)):
    """Return count of pending executions by status."""
    all_pending = db.query(PendingExecution).all()
    counts: dict[str, int] = {}
    for p in all_pending:
        counts[p.status] = counts.get(p.status, 0) + 1

    return {
        "success": True,
        "data": {
            "PENDING": counts.get("PENDING", 0),
            "EXECUTED": counts.get("EXECUTED", 0),
            "CANCELLED": counts.get("CANCELLED", 0),
            "total": len(all_pending),
        },
    }


@router.post("/{pending_id}/cancel")
def cancel_pending(pending_id: int, db: Session = Depends(get_db)):
    """Cancel a specific pending execution before it fires."""
    ok = cancel_pending_execution(db, pending_id)
    if not ok:
        return {"success": False, "error": f"Pending execution {pending_id} not found or not PENDING"}
    return {"success": True, "data": {"message": f"Pending execution {pending_id} cancelled"}}
