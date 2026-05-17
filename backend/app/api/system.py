"""System configuration and DB health endpoints."""

import time
from fastapi import APIRouter
from sqlalchemy import text
from app.core.config import settings
from app.db.database import check_db_connection, engine

router = APIRouter(prefix="/system", tags=["system"])

_REQUIRED_TABLES = [
    "candles", "signals", "paper_trades", "paper_portfolio",
    "paper_positions", "pending_executions", "equity_snapshots",
    "strategies", "watchlists", "scheduler_runs",
]


@router.get("/config-check")
def config_check():
    symbols = settings.scheduler_symbols_list

    db_ok = False
    try:
        check_db_connection()
        db_ok = True
    except Exception:
        pass

    market_calendar_ok = False
    try:
        from zoneinfo import ZoneInfo
        ZoneInfo("Asia/Kolkata")
        market_calendar_ok = True
    except Exception:
        pass

    return {
        "success": True,
        "data": {
            "auto_execution_enabled": settings.auto_execution_enabled,
            "scheduler_enabled": settings.scheduler_enabled,
            "symbol_count": len(symbols),
            "symbols": symbols,
            "db_connected": db_ok,
            "market_calendar_loaded": market_calendar_ok,
            "paper_trading": settings.paper_trading,
        },
    }


@router.get("/db-health")
def db_health():
    # DB latency check
    t0 = time.time()
    db_ok = False
    latency_ms = None
    try:
        check_db_connection()
        latency_ms = round((time.time() - t0) * 1000, 1)
        db_ok = True
    except Exception:
        pass

    # Table presence + row counts
    table_status: dict[str, bool] = {}
    row_counts: dict[str, int] = {}
    try:
        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            ))
            existing = {row[0] for row in result}
            for t in _REQUIRED_TABLES:
                table_status[t] = t in existing
            for t in [t for t in _REQUIRED_TABLES if table_status.get(t)]:
                row_counts[t] = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar() or 0
    except Exception:
        pass

    # Latest scheduler run
    latest_run = None
    try:
        with engine.connect() as conn:
            row = conn.execute(text(
                "SELECT job_id, started_at, finished_at, status, errors "
                "FROM scheduler_runs ORDER BY started_at DESC LIMIT 1"
            )).fetchone()
            if row:
                latest_run = {
                    "job_id": row[0],
                    "started_at": str(row[1]),
                    "finished_at": str(row[2]) if row[2] else None,
                    "status": row[3],
                    "errors": row[4],
                }
    except Exception:
        pass

    all_tables_ok = bool(table_status) and all(table_status.values())

    return {
        "success": True,
        "data": {
            "db_connected": db_ok,
            "latency_ms": latency_ms,
            "all_tables_present": all_tables_ok,
            "tables": table_status,
            "row_counts": row_counts,
            "latest_scheduler_run": latest_run,
        },
    }
