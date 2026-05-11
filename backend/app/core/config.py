"""
Centralized configuration management.
All settings loaded from environment variables - never hardcoded.
"""

import os
import sys
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # PAPER TRADING SAFETY GATE - must be true to start
    paper_trading: bool = Field(default=True, alias="PAPER_TRADING")

    # App
    app_name: str = Field(default="Algo Trading (Paper Only)", alias="APP_NAME")
    debug: bool = Field(default=False, alias="DEBUG")

    # Server - bind to localhost only during development
    host: str = Field(default="127.0.0.1", alias="HOST")
    port: int = Field(default=8000, alias="PORT")

    # Database
    database_url: str = Field(
        default="sqlite:///./trading.db",
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

    # HTTP client timeouts (seconds)
    http_timeout: int = Field(default=10, alias="HTTP_TIMEOUT")
    http_max_retries: int = Field(default=3, alias="HTTP_MAX_RETRIES")

    # Optional market data API key - fetched from env, never hardcoded
    market_data_api_key: str = Field(default="", alias="MARKET_DATA_API_KEY")
    market_data_base_url: str = Field(
        default="https://api.example.com",
        alias="MARKET_DATA_BASE_URL",
    )

    model_config = {"env_file": ".env", "populate_by_name": True, "extra": "ignore"}


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
