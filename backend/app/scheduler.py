"""
APScheduler setup.
Runs the signal generation cycle in-process on a fixed interval.
No Celery, no Redis, no distributed infrastructure.

Schedule:
  - Every 15 minutes during Indian market hours (09:15–15:30 IST, Mon–Fri)
  - Daily candles: once at 16:00 IST (10:30 UTC) after market close

The intraday cron trigger fires every 15 min across 09:00–15:59 IST.
A lightweight guard inside the job discards the 15:45 invocation so the
effective window is exactly 09:15–15:30 (NSE market hours).

Threading lock (_cycle_lock) ensures only one cycle runs at a time.
If the previous cycle is still running when the next trigger fires, the
new invocation is skipped and a SCHEDULER_OVERLAP_SKIPPED event is emitted.
"""

import threading
from datetime import datetime, time as dtime, timezone
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.logging import get_logger
from app.db.database import SessionLocal

logger = get_logger(__name__)

_scheduler: BackgroundScheduler | None = None
_cycle_lock = threading.Lock()

_IST = ZoneInfo("Asia/Kolkata")
_MARKET_OPEN  = dtime(9, 15)   # NSE opens 09:15 IST
_MARKET_CLOSE = dtime(15, 30)  # NSE closes 15:30 IST


def _is_within_market_hours() -> bool:
    """Return True if the current IST time falls within NSE market hours."""
    return _MARKET_OPEN <= datetime.now(_IST).time() <= _MARKET_CLOSE


def _record_run(db, job_id: str):
    """Create a SchedulerRun row and return it."""
    from app.models.scheduler_run import SchedulerRun
    run = SchedulerRun(
        job_id=job_id,
        started_at=datetime.now(timezone.utc).replace(tzinfo=None),
        status="RUNNING",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _finish_run(db, run, summary: dict) -> None:
    run.finished_at      = datetime.now(timezone.utc).replace(tzinfo=None)
    run.status           = "COMPLETED"
    run.symbols_processed = summary.get("symbols_processed", 0)
    run.candles_inserted  = summary.get("candles_inserted", 0)
    run.signals_generated = summary.get("signals_generated", 0)
    run.pending_executed  = summary.get("pending_executed", 0)
    run.errors            = summary.get("errors", 0)
    run.stale_skips       = summary.get("stale_skips", 0)
    run.duplicate_blocks  = summary.get("duplicate_blocks", 0)
    db.commit()


def _fail_run(db, run, exc: Exception) -> None:
    run.finished_at  = datetime.now(timezone.utc).replace(tzinfo=None)
    run.status       = "FAILED"
    run.error_detail = str(exc)[:500]
    try:
        db.commit()
    except Exception:
        db.rollback()


def _run_cycle_guarded(job_id: str, timeframes: list[str] | None = None) -> None:
    """
    Common wrapper for intraday and daily jobs.
    Acquires the in-process cycle lock to prevent overlapping runs.
    Records the cycle in scheduler_runs and emits execution events.
    """
    from app.services.scheduler_service import run_cycle
    from app.services import event_service as ev

    if not _cycle_lock.acquire(blocking=False):
        logger.warning("scheduler_cycle_overlap_skipped", job_id=job_id)
        # Emit overlap event without a DB session to avoid table-lock issues
        db = SessionLocal()
        try:
            ev.emit(db, ev.SCHEDULER_OVERLAP_SKIPPED,
                    details={"job_id": job_id})
        finally:
            db.close()
        return

    db = SessionLocal()
    run = _record_run(db, job_id)
    try:
        summary = run_cycle(db, timeframes=timeframes)
        _finish_run(db, run, summary)

        if summary.get("errors", 0) > 0:
            ev.emit(db, ev.SCHEDULER_FAILED,
                    details={"job_id": job_id, "errors": summary["errors"],
                             "cycle_id": summary.get("cycle_id")})
    except Exception as exc:
        logger.error("scheduler_job_failed", job_id=job_id, error_type=type(exc).__name__)
        _fail_run(db, run, exc)
        try:
            ev.emit(db, ev.SCHEDULER_FAILED,
                    details={"job_id": job_id, "error": str(exc)[:200]})
        except Exception:
            pass
    finally:
        db.close()
        _cycle_lock.release()


def _run_intraday_cycle() -> None:
    """Job: fetch + signal for 15m and 1h candles."""
    from app.core.config import settings
    if not settings.scheduler_enabled:
        return
    if not _is_within_market_hours():
        logger.debug("scheduler_skipped_outside_market_hours")
        return
    _run_cycle_guarded("intraday_cycle")


def _run_daily_cycle() -> None:
    """Job: fetch + signal for 1d candles after market close (16:00 IST).
    Intentionally skips the market-hours guard — this job runs after close by design.
    """
    from app.core.config import settings
    if not settings.scheduler_enabled:
        return
    _run_cycle_guarded("daily_cycle", timeframes=["1d"])


def start_scheduler() -> None:
    global _scheduler

    from app.core.config import settings
    if not settings.scheduler_enabled:
        logger.info("scheduler_disabled")
        return

    _scheduler = BackgroundScheduler(timezone="Asia/Kolkata")

    # Intraday: every 15 minutes, Mon–Fri, hours 9–15.
    # The _is_within_market_hours() guard inside the job filters out 15:45.
    _scheduler.add_job(
        _run_intraday_cycle,
        trigger=CronTrigger(
            day_of_week="mon-fri",
            hour="9-15",
            minute="*/15",
            timezone="Asia/Kolkata",
        ),
        id="intraday_cycle",
        replace_existing=True,
        misfire_grace_time=60,
        max_instances=1,   # APScheduler-level duplicate prevention (belt)
    )

    # Daily: once at 16:00 IST after market close
    _scheduler.add_job(
        _run_daily_cycle,
        trigger=CronTrigger(
            day_of_week="mon-fri",
            hour=16,
            minute=0,
            timezone="Asia/Kolkata",
        ),
        id="daily_cycle",
        replace_existing=True,
        misfire_grace_time=300,
        max_instances=1,
    )

    _scheduler.start()
    logger.info(
        "scheduler_started",
        jobs=["intraday_cycle (every 15min, market hours)", "daily_cycle (16:00 IST)"],
    )


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("scheduler_stopped")
    _scheduler = None


def get_scheduler() -> BackgroundScheduler | None:
    return _scheduler
