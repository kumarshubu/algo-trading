"""
Centralized exception handling.
Never returns stack traces to the frontend.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from app.core.logging import get_logger

logger = get_logger(__name__)


class TradingError(Exception):
    """Base error for trading-related failures."""
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class InsufficientBalanceError(TradingError):
    def __init__(self, message: str = "Insufficient virtual balance"):
        super().__init__(message, status_code=400)


class MaxPositionsError(TradingError):
    def __init__(self, message: str = "Maximum simultaneous positions reached"):
        super().__init__(message, status_code=400)


class MaxDailyLossError(TradingError):
    def __init__(self, message: str = "Maximum daily loss limit reached"):
        super().__init__(message, status_code=400)


class StrategyKillSwitchError(TradingError):
    def __init__(self, message: str = "Strategy is disabled via kill switch"):
        super().__init__(message, status_code=403)


class DuplicateSignalTradeError(TradingError):
    """Raised when a trade for this signal_id already exists (crash-recovery duplicate)."""
    def __init__(self, signal_id: int):
        super().__init__(f"Trade for signal {signal_id} already exists", status_code=409)
        self.signal_id = signal_id


class MarketDataError(Exception):
    """Raised when market data fetch fails."""
    pass


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(TradingError)
    async def trading_error_handler(request: Request, exc: TradingError) -> JSONResponse:
        logger.warning("trading_error", message=exc.message, path=str(request.url))
        return JSONResponse(
            status_code=exc.status_code,
            content={"success": False, "error": exc.message},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        logger.warning("validation_error", path=str(request.url))
        return JSONResponse(
            status_code=422,
            content={"success": False, "error": "Validation failed", "details": exc.errors()},
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
        # Log full error server-side but never expose stack trace to client
        logger.error("unhandled_exception", exc_type=type(exc).__name__, path=str(request.url))
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": "Internal server error"},
        )
