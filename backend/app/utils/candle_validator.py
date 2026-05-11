"""
Candle validation utilities.
All rules enforced before any candle touches the database.
"""

from datetime import datetime, timezone
from dataclasses import dataclass

from app.schemas.candle import CandleCreate
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ValidationResult:
    valid: list[CandleCreate]
    rejected: int
    reasons: dict[str, int]  # reason -> count


def validate_candles(candles: list[CandleCreate], symbol: str = "") -> ValidationResult:
    """
    Validate a list of candles against all business rules.
    Returns valid candles and a summary of rejections.
    """
    valid: list[CandleCreate] = []
    reasons: dict[str, int] = {}
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)

    for c in candles:
        reason = _check(c, now_utc)
        if reason is None:
            valid.append(c)
        else:
            reasons[reason] = reasons.get(reason, 0) + 1

    rejected = len(candles) - len(valid)
    if rejected > 0:
        logger.warning(
            "candles_validation_rejected",
            symbol=symbol,
            total=len(candles),
            rejected=rejected,
            reasons=reasons,
        )

    return ValidationResult(valid=valid, rejected=rejected, reasons=reasons)


def _check(c: CandleCreate, now_utc: datetime) -> str | None:
    """Return a rejection reason string, or None if the candle is valid."""

    # 1. No null / zero OHLC values
    if any(v is None or v != v for v in (c.open, c.high, c.low, c.close)):
        return "null_ohlc"
    if c.open <= 0 or c.high <= 0 or c.low <= 0 or c.close <= 0:
        return "zero_or_negative_price"

    # 2. No negative volume
    if c.volume is None or c.volume < 0:
        return "negative_volume"

    # 3. No future timestamps
    ts = c.timestamp_utc
    if hasattr(ts, "tzinfo") and ts.tzinfo is not None:
        ts = ts.replace(tzinfo=None)
    if ts > now_utc:
        return "future_timestamp"

    # 4. Valid OHLC relationships
    if c.high < c.open:
        return "high_lt_open"
    if c.high < c.close:
        return "high_lt_close"
    if c.low > c.open:
        return "low_gt_open"
    if c.low > c.close:
        return "low_gt_close"

    return None


def is_valid_candle(c: CandleCreate) -> bool:
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    return _check(c, now_utc) is None
