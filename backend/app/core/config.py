"""
Centralized configuration management.
All settings loaded from environment variables - never hardcoded.
"""

import os
import sys
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field

# Resolve .env from project root regardless of working directory
_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    # PAPER TRADING SAFETY GATE - must be true to start
    paper_trading: bool = Field(default=True, alias="PAPER_TRADING")

    # API authentication - set a strong random value in production.
    # Leave empty to disable auth (dev/local use only).
    api_key: str = Field(default="", alias="API_KEY")

    # App
    app_name: str = Field(default="Algo Trading (Paper Only)", alias="APP_NAME")
    debug: bool = Field(default=False, alias="DEBUG")

    # Server - bind to localhost only during development
    host: str = Field(default="127.0.0.1", alias="HOST")
    port: int = Field(default=8000, alias="PORT")

    # Database
    database_url: str = Field(
        default="",
        alias="DATABASE_URL",
    )

    # CORS - frontend origin
    cors_origins: str = Field(
        default="http://localhost:3000",
        alias="CORS_ORIGINS",
    )

    # Paper trading defaults
    initial_virtual_balance_inr: float = Field(
        default=100000.0,
        alias="INITIAL_VIRTUAL_BALANCE_INR",
    )
    max_capital_per_trade_pct: float = Field(
        default=0.10,  # 10% of balance per trade
        alias="MAX_CAPITAL_PER_TRADE_PCT",
    )
    max_simultaneous_positions: int = Field(
        default=5,
        alias="MAX_SIMULTANEOUS_POSITIONS",
    )
    max_daily_loss_pct: float = Field(
        default=0.05,  # 5% of balance
        alias="MAX_DAILY_LOSS_PCT",
    )
    slippage_pct: float = Field(
        default=0.001,  # 0.1% slippage
        alias="SLIPPAGE_PCT",
    )
    brokerage_pct: float = Field(
        default=0.0003,  # 0.03% brokerage
        alias="BROKERAGE_PCT",
    )

    # Scheduler
    scheduler_enabled: bool = Field(default=True, alias="SCHEDULER_ENABLED")
    # Auto execution: if true, scheduler will execute BUY signals as paper trades automatically.
    # Default false — review signals manually first.
    auto_execution_enabled: bool = Field(default=False, alias="AUTO_EXECUTION_ENABLED")
    # Symbols the scheduler evaluates (comma-separated)
    scheduler_symbols: str = Field(
        default="RELIANCE,TCS,INFY,HDFCBANK,ICICIBANK",
        alias="SCHEDULER_SYMBOLS",
    )

    # HTTP client timeouts (seconds)
    http_timeout: int = Field(default=10, alias="HTTP_TIMEOUT")
    http_max_retries: int = Field(default=3, alias="HTTP_MAX_RETRIES")

    # Server-side request timeout (seconds) — kills hung handlers (e.g. stuck yfinance calls)
    request_timeout: int = Field(default=60, alias="REQUEST_TIMEOUT")

    # Optional market data API key - fetched from env, never hardcoded
    market_data_api_key: str = Field(default="", alias="MARKET_DATA_API_KEY")
    market_data_base_url: str = Field(
        default="https://api.example.com",
        alias="MARKET_DATA_BASE_URL",
    )

    model_config = {"env_file": str(_ENV_FILE), "populate_by_name": True, "extra": "ignore"}


def load_settings() -> Settings:
    settings = Settings()

    # Safety gate: refuse to start if PAPER_TRADING is not true
    if not settings.paper_trading:
        print(
            "FATAL: PAPER_TRADING environment variable is not set to true. "
            "This platform only supports paper trading. "
            "Set PAPER_TRADING=true in your .env file to start.",
            file=sys.stderr,
        )
        sys.exit(1)

    return settings


# Single shared instance
settings = load_settings()
