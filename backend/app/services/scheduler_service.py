"""
Scheduler cycle logic.

Updated flow (next-candle execution):
  1. fetch + store candles
  2. check candle freshness — skip stale symbols during market hours
  3. generate signals
  4. create pending executions for new BUY/SELL signals
  5. process executable pending executions
  6. check open positions (stop loss / target)
  7. take equity snapshot

Pure functions — APScheduler setup lives in app/scheduler.py.
"""

import uuid
from datetime import datetime, time as dtime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.services.market_data_service import fetch_candles
from app.services.candle_service import bulk_upsert_candles, get_candles, get_latest_candle
from app.services.signal_service import save_signal
from app.services import event_service as ev
from app.strategies.ema_rsi_volume import EmaRsiVolumeStrategy

logger = get_logger(__name__)

TIMEFRAMES = ["15m", "1h", "1d"]
MIN_CANDLES_REQUIRED = 60

# Stale-candle thresholds (minutes). If the latest candle is older than this
# during market hours, execution is skipped and a STALE_DATA event is emitted.
_STALE_THRESHOLDS: dict[str, Optional[int]] = {
    "15m": 20,
    "1h": 65,
    "1d": None,  # daily candles are refreshed once at market close — never stale intraday
}

_IST = ZoneInfo("Asia/Kolkata")
_MARKET_OPEN  = dtime(9, 15)
_MARKET_CLOSE = dtime(15, 30)

_strategy = EmaRsiVolumeStrategy()


def _is_market_hours() -> bool:
    return _MARKET_OPEN <= datetime.now(_IST).time() <= _MARKET_CLOSE


def _check_freshness(
    db: Session,
    symbol: str,
    timeframe: str,
) -> tuple[bool, Optional[float]]:
    """
    Returns (is_stale, lag_minutes).
    During market hours, checks if the latest candle is within the threshold.
    Outside market hours always returns (False, lag).
    """
    threshold = _STALE_THRESHOLDS.get(timeframe)
    if threshold is None or not _is_market_hours():
        return False, None

    latest = get_latest_candle(db, symbol, timeframe)
    if not latest:
        return True, None

    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    lag_minutes = (now_utc - latest.timestamp_utc).total_seconds() / 60
    return lag_minutes > threshold, round(lag_minutes, 1)


def _get_symbols(db: Session) -> list[str]:
    """Return watchlist symbols; fall back to scheduler_symbols env var if empty."""
    from app.models.watchlist import Watchlist
    rows = db.query(Watchlist.symbol).all()
    if rows:
        return [r.symbol for r in rows]
    return [s.strip().upper() for s in settings.scheduler_symbols.split(",") if s.strip()]


def run_cycle(db: Session, timeframes: list[str] | None = None) -> dict:
    """
    Run one full scheduler cycle for all configured symbols and timeframes.
    Generates a UUID cycle_id for log correlation across all sub-operations.
    Safe to call repeatedly — idempotent by design.
    """
    cycle_id = str(uuid.uuid4())
    symbols = _get_symbols(db)
    _timeframes = timeframes or TIMEFRAMES

    summary = {
        "cycle_id": cycle_id,
        "symbols_processed": 0,
        "candles_inserted": 0,
        "signals_generated": 0,
        "signals_skipped_duplicate": 0,
        "pending_created": 0,
        "pending_executed": 0,
        "pending_cancelled": 0,
        "stale_skips": 0,
        "duplicate_blocks": 0,
        "positions_checked": 0,
        "stops_triggered": 0,
        "targets_hit": 0,
        "sell_signals_closed": 0,
        "errors": 0,
    }

    logger.info("scheduler_cycle_start", symbols=symbols, timeframes=_timeframes, cycle_id=cycle_id)

    # Steps 1–4: fetch candles, check freshness, generate signals, queue pending executions
    for symbol in symbols:
        for timeframe in _timeframes:
            try:
                result = _process_one(db, symbol, timeframe, cycle_id)
                summary["candles_inserted"] += result["inserted"]
                summary["signals_generated"] += result["signal_saved"]
                summary["signals_skipped_duplicate"] += result["signal_duplicate"]
                summary["pending_created"] += result["pending_created"]
                summary["sell_signals_closed"] += result["sell_signals_closed"]
                summary["stale_skips"] += result["stale_skipped"]
            except Exception as e:
                logger.error(
                    "scheduler_cycle_error",
                    symbol=symbol,
                    timeframe=timeframe,
                    error_type=type(e).__name__,
                    cycle_id=cycle_id,
                )
                summary["errors"] += 1
        summary["symbols_processed"] += 1

    # Step 5: process pending executions (execute at next candle open)
    try:
        from app.services.pending_execution_service import process_pending_executions
        pe_result = process_pending_executions(db, cycle_id=cycle_id)
        summary["pending_executed"]   = pe_result["executed"]
        summary["pending_cancelled"]  = pe_result["cancelled"]
        summary["duplicate_blocks"]  += pe_result.get("duplicate_blocked", 0)
    except Exception as e:
        logger.error("pending_execution_processing_failed", error_type=type(e).__name__, cycle_id=cycle_id)
        summary["errors"] += 1

    # Step 6: check open positions for stop loss / target
    try:
        from app.services.execution_service import check_and_update_positions
        pos_result = check_and_update_positions(db)
        summary["positions_checked"] = pos_result["checked"]
        summary["stops_triggered"]   = pos_result["stopped"]
        summary["targets_hit"]       = pos_result["target_hit"]
    except Exception as e:
        logger.error("position_check_failed", error_type=type(e).__name__, cycle_id=cycle_id)
        summary["errors"] += 1

    # Step 7: equity snapshot
    try:
        from app.services.execution_service import take_equity_snapshot
        take_equity_snapshot(db)
    except Exception as e:
        logger.error("equity_snapshot_failed", error_type=type(e).__name__, cycle_id=cycle_id)

    logger.info("scheduler_cycle_complete", **summary)
    return summary


def _process_one(db: Session, symbol: str, timeframe: str, cycle_id: str) -> dict:
    """
    Fetch → validate → freshness check → store → evaluate → persist signal → queue.
    Returns per-symbol-timeframe counts for the scheduler summary.
    """
    result = {
        "inserted": 0,
        "signal_saved": 0,
        "signal_duplicate": 0,
        "pending_created": 0,
        "sell_signals_closed": 0,
        "stale_skipped": 0,
    }

    _raw, validation = fetch_candles(symbol, timeframe)

    if validation.valid:
        result["inserted"] = bulk_upsert_candles(db, validation.valid)

    # ── Stale-candle guard ───────────────────────────────────────────────────
    is_stale, lag_minutes = _check_freshness(db, symbol, timeframe)
    if is_stale:
        logger.warning(
            "stale_candle_skipped",
            symbol=symbol,
            timeframe=timeframe,
            lag_minutes=lag_minutes,
            cycle_id=cycle_id,
        )
        ev.emit(db, ev.STALE_DATA, symbol=symbol, cycle_id=cycle_id,
                details={"timeframe": timeframe, "lag_minutes": lag_minutes})
        result["stale_skipped"] = 1
        return result

    stored = get_candles(db, symbol=symbol, timeframe=timeframe, limit=200)
    if len(stored) < MIN_CANDLES_REQUIRED:
        logger.debug(
            "scheduler_skip_insufficient_data",
            symbol=symbol, timeframe=timeframe,
            have=len(stored), need=MIN_CANDLES_REQUIRED,
        )
        return result

    df = pd.DataFrame(
        [{"open": c.open, "high": c.high, "low": c.low, "close": c.close, "volume": c.volume}
         for c in stored],
        index=pd.DatetimeIndex([c.timestamp_utc for c in stored]),
    )

    trade_signal = _strategy.generate_signal(symbol, df)
    candle_ts = stored[-1].timestamp_utc

    saved_signal = save_signal(
        db=db,
        symbol=symbol,
        timeframe=timeframe,
        strategy_name=_strategy.name,
        signal_type=trade_signal.signal.value,
        candle_timestamp=candle_ts,
        metadata={
            "price": trade_signal.price,
            "stop_loss": trade_signal.stop_loss,
            "target_price": trade_signal.target_price,
            "reason": trade_signal.reason,
        },
    )

    if saved_signal:
        result["signal_saved"] = 1
        if saved_signal.signal_type == "BUY" and settings.auto_execution_enabled:
            from app.services.pending_execution_service import create_pending_execution
            if create_pending_execution(db, saved_signal):
                result["pending_created"] = 1
        elif saved_signal.signal_type == "SELL":
            from app.services.pending_execution_service import create_pending_execution
            if create_pending_execution(db, saved_signal):
                result["pending_created"] = 1
    else:
        result["signal_duplicate"] = 1

    return result


def get_candle_freshness(db: Session, symbols: list[str]) -> dict:
    """
    Return freshness status for each symbol across all timeframes.
    Used by GET /api/v1/candles/freshness.
    """
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    result: dict[str, dict] = {}

    for symbol in symbols:
        result[symbol] = {}
        for timeframe in TIMEFRAMES:
            threshold = _STALE_THRESHOLDS.get(timeframe)
            latest = get_latest_candle(db, symbol, timeframe)
            if not latest:
                result[symbol][timeframe] = {
                    "fresh": False,
                    "last_candle": None,
                    "lag_minutes": None,
                    "threshold_minutes": threshold,
                }
                continue

            lag_minutes = round((now_utc - latest.timestamp_utc).total_seconds() / 60, 1)
            fresh = (threshold is None) or (lag_minutes <= threshold)
            result[symbol][timeframe] = {
                "fresh": fresh,
                "last_candle": latest.timestamp_utc.isoformat(),
                "lag_minutes": lag_minutes,
                "threshold_minutes": threshold,
            }

    return result
