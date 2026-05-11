"""
APScheduler setup.
Runs the signal generation cycle in-process on a fixed interval.
No Celery, no Redis, no distributed infrastructure.

Schedule:
  - Every 15 minutes during Indian market hours (09:15–15:30 IST, Mon–Fri)
  - Daily candles: once at 16:00 IST (10:30 UTC) after market close

The cycle itself is safe to run off-hours — it will simply fetch the latest
available data and generate a signal. Idempotency prevents duplicate signals.
"""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.logging import get_logger
from app.db.database import SessionLocal

logger = get_logger(__name__)

_scheduler: BackgroundScheduler | None = None


def _run_intraday_cycle() -> None:
    """Job: fetch + signal for 15m and 1h candles."""
    from app.services.scheduler_service import run_cycle
    from app.core.config import settings

    if not settings.scheduler_enabled:
        return

    db = SessionLocal()
    try:
        run_cycle(db)
    except Exception as e:
        logger.error("scheduler_job_failed", error_type=type(e).__name__)
    finally:
        db.close()


def _run_daily_cycle() -> None:
    """Job: fetch + signal for 1d candles after market close."""
    # Daily is also handled by run_cycle — no separate logic needed
    _run_intraday_cycle()


def start_scheduler() -> None:
    global _scheduler

    from app.core.config import settings
    if not settings.scheduler_enabled:
        logger.info("scheduler_disabled")
        return

    _scheduler = BackgroundScheduler(timezone="Asia/Kolkata")

    # Intraday: every 15 minutes, Mon–Fri, during market hours
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
