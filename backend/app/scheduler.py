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

The cycle itself is safe to run off-hours — it will simply fetch the latest
available data and generate a signal. Idempotency prevents duplicate signals.
"""

from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.logging import get_logger
from app.db.database import SessionLocal

logger = get_logger(__name__)

_scheduler: BackgroundScheduler | None = None

_IST = ZoneInfo("Asia/Kolkata")
_MARKET_OPEN  = dtime(9, 15)   # NSE opens 09:15 IST
_MARKET_CLOSE = dtime(15, 30)  # NSE closes 15:30 IST


def _is_within_market_hours() -> bool:
    """Return True if the current IST time falls within NSE market hours."""
    return _MARKET_OPEN <= datetime.now(_IST).time() <= _MARKET_CLOSE


def _run_intraday_cycle() -> None:
    """Job: fetch + signal for 15m and 1h candles."""
    from app.services.scheduler_service import run_cycle
    from app.core.config import settings

    if not settings.scheduler_enabled:
        return

    # The cron trigger fires at :00/:15/:30/:45 for hours 9–15, which means it
    # also fires at 15:45 — after market close.  The guard below discards that
    # invocation without touching the database.
    if not _is_within_market_hours():
        logger.debug("scheduler_skipped_outside_market_hours")
        return

    db = SessionLocal()
    try:
        run_cycle(db)
    except Exception as e:
        logger.error("scheduler_job_failed", error_type=type(e).__name__)
    finally:
        db.close()


def _run_daily_cycle() -> None:
    """Job: fetch + signal for 1d candles after market close (16:00 IST).
    Intentionally skips the market-hours guard — this job runs after close by design.
    """
    from app.services.scheduler_service import run_cycle
    from app.core.config import settings

    if not settings.scheduler_enabled:
        return

    db = SessionLocal()
    try:
        run_cycle(db, timeframes=["1d"])
    except Exception as e:
        logger.error("scheduler_daily_job_failed", error_type=type(e).__name__)
    finally:
        db.close()


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
