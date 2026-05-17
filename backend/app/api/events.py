"""
Execution event endpoints.
Provides recent event history and an SSE stream for real-time monitoring.
"""

import asyncio
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.database import get_db, SessionLocal
from app.services import event_service as ev

router = APIRouter(prefix="/events", tags=["events"])


def _serialize_event(event) -> dict:
    return {
        "id": event.id,
        "event_type": event.event_type,
        "symbol": event.symbol,
        "strategy_name": event.strategy_name,
        "cycle_id": event.cycle_id,
        "details": json.loads(event.details_json) if event.details_json else None,
        "created_at": event.created_at.isoformat() if isinstance(event.created_at, datetime) else str(event.created_at),
    }


@router.get("/recent")
def recent_events(
    limit: int = Query(default=50, ge=1, le=500),
    event_type: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Return the most recent execution events, newest first.
    Optional event_type filter: BUY_EXECUTED, SELL_EXECUTED, STOP_LOSS_TRIGGERED,
    TARGET_HIT, STALE_DATA, DUPLICATE_BLOCKED, CRASH_RECOVERED, SCHEDULER_FAILED,
    SCHEDULER_OVERLAP_SKIPPED.
    """
    events = ev.get_recent(db, limit=limit, event_type=event_type)
    return {
        "success": True,
        "data": [_serialize_event(e) for e in events],
    }


@router.get("/metrics")
def scheduler_metrics(db: Session = Depends(get_db)):
    """
    Aggregate scheduler metrics for the last 24 hours of scheduler runs.
    """
    from datetime import timedelta, timezone
    from sqlalchemy import func, text
    from app.models.scheduler_run import SchedulerRun
    from app.models.execution_event import ExecutionEvent

    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=24)

    runs = (
        db.query(SchedulerRun)
        .filter(SchedulerRun.started_at >= cutoff)
        .order_by(SchedulerRun.started_at.desc())
        .all()
    )

    completed = [r for r in runs if r.status == "COMPLETED"]
    failed    = [r for r in runs if r.status == "FAILED"]

    # Average cycle latency (seconds)
    latencies = [
        (r.finished_at - r.started_at).total_seconds()
        for r in completed
        if r.finished_at
    ]
    avg_latency_s = round(sum(latencies) / len(latencies), 1) if latencies else None

    # Event counts in last 24h
    def _count(event_type: str) -> int:
        return (
            db.query(func.count(ExecutionEvent.id))
            .filter(ExecutionEvent.event_type == event_type,
                    ExecutionEvent.created_at >= cutoff)
            .scalar() or 0
        )

    return {
        "success": True,
        "data": {
            "period_hours": 24,
            "total_cycles": len(runs),
            "completed_cycles": len(completed),
            "failed_cycles": len(failed),
            "avg_cycle_latency_s": avg_latency_s,
            "trades_executed": _count(ev.BUY_EXECUTED) + _count(ev.SELL_EXECUTED),
            "buys_executed": _count(ev.BUY_EXECUTED),
            "sells_executed": _count(ev.SELL_EXECUTED),
            "stops_triggered": _count(ev.STOP_LOSS_TRIGGERED),
            "stale_skips": _count(ev.STALE_DATA),
            "duplicate_blocks": _count(ev.DUPLICATE_BLOCKED),
            "crash_recoveries": _count(ev.CRASH_RECOVERED),
            "overlap_skips": _count(ev.SCHEDULER_OVERLAP_SKIPPED),
        },
    }


@router.get("/stream")
async def events_stream(request: Request):
    """
    Server-Sent Events stream. Polls for new execution events every 3 seconds.
    Connect once; each new event is pushed as it lands in the DB.
    Sends a heartbeat comment every 3s to keep the connection alive.

    Usage:
        const es = new EventSource('/api/v1/events/stream', {
            headers: { 'X-API-Key': '...' }
        });
        es.onmessage = (e) => console.log(JSON.parse(e.data));
    """
    async def generator():
        last_id = 0
        # Prime last_id from the latest existing event so we only stream NEW events
        db = SessionLocal()
        try:
            from app.models.execution_event import ExecutionEvent
            latest = db.query(ExecutionEvent).order_by(ExecutionEvent.id.desc()).first()
            if latest:
                last_id = latest.id
        finally:
            db.close()

        while True:
            if await request.is_disconnected():
                break

            db = SessionLocal()
            try:
                from app.models.execution_event import ExecutionEvent
                new_events = (
                    db.query(ExecutionEvent)
                    .filter(ExecutionEvent.id > last_id)
                    .order_by(ExecutionEvent.id.asc())
                    .limit(50)
                    .all()
                )
                if new_events:
                    for event in new_events:
                        last_id = event.id
                        payload = json.dumps(_serialize_event(event))
                        yield f"data: {payload}\n\n"
                else:
                    # Heartbeat keeps the connection alive through proxies
                    yield ": heartbeat\n\n"
            except Exception:
                yield ": error\n\n"
            finally:
                db.close()

            await asyncio.sleep(3)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # disable nginx buffering
        },
    )
