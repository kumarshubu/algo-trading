"""
Scheduler cycle logic.

Updated flow (next-candle execution):
  1. fetch + store candles
  2. generate signals
  3. create pending executions for new BUY signals
  4. process executable pending executions
  5. check open positions (stop loss / target)
  6. take equity snapshot

Pure functions — APScheduler setup lives in app/scheduler.py.
"""

import pandas as pd
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.services.market_data_service import fetch_candles
from app.services.candle_service import bulk_upsert_candles, get_candles
from app.services.signal_service import save_signal
from app.strategies.ema_rsi_volume import EmaRsiVolumeStrategy

logger = get_logger(__name__)

TIMEFRAMES = ["15m", "1h", "1d"]
MIN_CANDLES_REQUIRED = 60

_strategy = EmaRsiVolumeStrategy()


def run_cycle(db: Session) -> dict:
    """
    Run one full scheduler cycle for all configured symbols and timeframes.
    Safe to call repeatedly — idempotent by design.
    """
    symbols = [s.strip().upper() for s in settings.scheduler_symbols.split(",") if s.strip()]

    summary = {
        "symbols_processed": 0,
        "candles_inserted": 0,
        "signals_generated": 0,
        "signals_skipped_duplicate": 0,
        "pending_created": 0,
        "pending_executed": 0,
        "pending_cancelled": 0,
        "positions_checked": 0,
        "stops_triggered": 0,
        "targets_hit": 0,
        "errors": 0,
    }

    logger.info("scheduler_cycle_start", symbols=symbols, timeframes=TIMEFRAMES)

    # Steps 1–3: fetch candles, generate signals, queue pending executions
    for symbol in symbols:
        for timeframe in TIMEFRAMES:
            try:
                result = _process_one(db, symbol, timeframe)
                summary["candles_inserted"] += result["inserted"]
                summary["signals_generated"] += result["signal_saved"]
                summary["signals_skipped_duplicate"] += result["signal_duplicate"]
                summary["pending_created"] += result["pending_created"]
            except Exception as e:
                logger.error(
                    "scheduler_cycle_error",
                    symbol=symbol,
                    timeframe=timeframe,
                    error_type=type(e).__name__,
                )
                summary["errors"] += 1
        summary["symbols_processed"] += 1

    # Step 4: process pending executions (execute at next candle open)
    try:
        from app.services.pending_execution_service import process_pending_executions
        pe_result = process_pending_executions(db)
        summary["pending_executed"] = pe_result["executed"]
        summary["pending_cancelled"] = pe_result["cancelled"]
    except Exception as e:
        logger.error("pending_execution_processing_failed", error_type=type(e).__name__)
        summary["errors"] += 1

    # Step 5: check open positions for stop loss / target
    try:
        from app.services.execution_service import check_and_update_positions
        pos_result = check_and_update_positions(db)
        summary["positions_checked"] = pos_result["checked"]
        summary["stops_triggered"] = pos_result["stopped"]
        summary["targets_hit"] = pos_result["target_hit"]
    except Exception as e:
        logger.error("position_check_failed", error_type=type(e).__name__)
        summary["errors"] += 1

    # Step 6: equity snapshot
    try:
        from app.services.execution_service import take_equity_snapshot
        take_equity_snapshot(db)
    except Exception as e:
        logger.error("equity_snapshot_failed", error_type=type(e).__name__)

    logger.info("scheduler_cycle_complete", **summary)
    return summary


def _process_one(db: Session, symbol: str, timeframe: str) -> dict:
    """
    Fetch → validate → store → evaluate → persist signal → create pending execution.
    Returns counts for the scheduler summary.
    """
    result = {"inserted": 0, "signal_saved": 0, "signal_duplicate": 0, "pending_created": 0}

    _raw, validation = fetch_candles(symbol, timeframe)

    if validation.valid:
        result["inserted"] = bulk_upsert_candles(db, validation.valid)

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
        # Create a pending execution only for new BUY signals
        if saved_signal.signal_type == "BUY":
            from app.services.pending_execution_service import create_pending_execution
            pending = create_pending_execution(db, saved_signal)
            if pending:
                result["pending_created"] = 1
    else:
        result["signal_duplicate"] = 1

    return result
