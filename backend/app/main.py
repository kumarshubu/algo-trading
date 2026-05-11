"""
Algo Trading Platform - FastAPI Application
PAPER TRADING ONLY - NO REAL EXECUTION
"""

import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import setup_logging, get_logger
from app.core.exceptions import register_exception_handlers
from app.db.database import engine, Base

# Import all models so SQLAlchemy registers their tables
from app.models import candle, trade, position, watchlist, strategy, portfolio, signal, equity_snapshot, pending_execution  # noqa: F401

# Import routers
from app.api import (
    health, candles, trading,
    watchlist as watchlist_api,
    strategies, backtesting, signals, market_data,
    scheduler as scheduler_api, paper_trades, pending_executions, analytics,
)

setup_logging(debug=settings.debug)
logger = get_logger(__name__)

# Schema is managed exclusively by Alembic (run: alembic upgrade head)
# create_all() is intentionally removed — it conflicts with migration history


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "server_started",
        app=settings.app_name,
        paper_trading=settings.paper_trading,
        scheduler_enabled=settings.scheduler_enabled,
    )
    from app.scheduler import start_scheduler, stop_scheduler
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title=settings.app_name,
    description="Paper trading platform for learning algo trading. NOT for real trading.",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS - only allow the configured frontend origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "Accept"],
)

register_exception_handlers(app)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration_ms = round((time.time() - start) * 1000, 1)
    logger.info(
        "http_request",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration_ms=duration_ms,
    )
    return response


app.include_router(health.router)
app.include_router(candles.router, prefix="/api/v1")
app.include_router(trading.router, prefix="/api/v1")
app.include_router(watchlist_api.router, prefix="/api/v1")
app.include_router(strategies.router, prefix="/api/v1")
app.include_router(backtesting.router, prefix="/api/v1")
app.include_router(signals.router, prefix="/api/v1")
app.include_router(market_data.router, prefix="/api/v1")
app.include_router(scheduler_api.router, prefix="/api/v1")
app.include_router(paper_trades.router, prefix="/api/v1")
app.include_router(pending_executions.router, prefix="/api/v1")
app.include_router(analytics.router, prefix="/api/v1")
