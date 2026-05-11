"""
Retry with exponential backoff for external HTTP calls.
Used by market data service to handle transient failures.
"""

import asyncio
from typing import Callable, TypeVar
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)
import logging

from app.core.logging import get_logger

logger = get_logger(__name__)
_std_logger = logging.getLogger(__name__)

T = TypeVar("T")


def with_retry(max_attempts: int = 3, min_wait: float = 1.0, max_wait: float = 10.0):
    """Decorator factory for HTTP retry with exponential backoff."""
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
        retry=retry_if_exception_type((Exception,)),
        before_sleep=before_sleep_log(_std_logger, logging.WARNING),
        reraise=True,
    )
