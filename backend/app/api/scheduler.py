"""
Scheduler control API.
POST /api/v1/scheduler/run-once  — manually trigger one full cycle
GET  /api/v1/scheduler/status    — check scheduler state
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.core.config import settings
from app.core.logging import get_logger

router = APIRouter(prefix="/scheduler", tags=["scheduler"])
logger = get_logger(__name__)


@router.post("/run-once")
def run_once(db: Session = Depends(get_db)):
    """
    Manually trigger one full scheduler cycle.
    Useful for testing or backfilling signals outside market hours.
    """
    from app.services.scheduler_service import run_cycle
    logger.info("scheduler_manual_trigger")
    summary = run_cycle(db)
    return {"success": True, "data": summary}


@router.get("/status")
def scheduler_status():
    """Return whether the scheduler is running and list its jobs."""
    from app.scheduler import get_scheduler
    sched = get_scheduler()

    if sched is None or not sched.running:
        return {
            "success": True,
            "data": {
                "running": False,
                "enabled": settings.scheduler_enabled,
                "jobs": [],
            },
        }

    jobs = [
        {
            "id": job.id,
            "next_run": str(job.next_run_time) if job.next_run_time else None,
            "trigger": str(job.trigger),
        }
        for job in sched.get_jobs()
    ]
    return {
        "success": True,
        "data": {
            "running": True,
            "enabled": settings.scheduler_enabled,
            "jobs": jobs,
        },
    }
