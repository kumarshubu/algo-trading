"""
Execution event persistence helpers.
All calls are fire-and-commit — never raise, never block execution flow.
"""

import json
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.execution_event import ExecutionEvent

logger = get_logger(__name__)

# ── event type constants ──────────────────────────────────────────────────────
BUY_EXECUTED               = "BUY_EXECUTED"
SELL_EXECUTED              = "SELL_EXECUTED"
STOP_LOSS_TRIGGERED        = "STOP_LOSS_TRIGGERED"
TARGET_HIT                 = "TARGET_HIT"
SCHEDULER_FAILED           = "SCHEDULER_FAILED"
STALE_DATA                 = "STALE_DATA"
DUPLICATE_BLOCKED          = "DUPLICATE_BLOCKED"
CRASH_RECOVERED            = "CRASH_RECOVERED"
SCHEDULER_OVERLAP_SKIPPED  = "SCHEDULER_OVERLAP_SKIPPED"


def emit(
    db: Session,
    event_type: str,
    symbol: Optional[str] = None,
    strategy_name: Optional[str] = None,
    cycle_id: Optional[str] = None,
    details: Optional[dict] = None,
) -> None:
    """
    Persist one execution event. Never raises — log and swallow any DB error
    so a telemetry failure never interrupts trading logic.
    """
    try:
        ev = ExecutionEvent(
            event_type=event_type,
            symbol=symbol,
            strategy_name=strategy_name,
            cycle_id=cycle_id,
            details_json=json.dumps(details) if details else None,
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        db.add(ev)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning("event_emit_failed", event_type=event_type, error=str(exc))


def get_recent(db: Session, limit: int = 100, event_type: Optional[str] = None) -> list[ExecutionEvent]:
    query = db.query(ExecutionEvent)
    if event_type:
        query = query.filter(ExecutionEvent.event_type == event_type)
    return query.order_by(ExecutionEvent.created_at.desc()).limit(min(limit, 500)).all()
