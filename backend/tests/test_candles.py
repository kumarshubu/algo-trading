"""Tests for candle storage service."""

from datetime import datetime
from unittest.mock import patch

from app.services.candle_service import (
    upsert_candle,
    bulk_upsert_candles,
    get_candles,
    get_candle_count,
)
from app.schemas.candle import CandleCreate


def _make_candle(symbol="TEST", timeframe="1h", offset_hours=0):
    return CandleCreate(
        symbol=symbol,
        timeframe=timeframe,
        timestamp_utc=datetime(2024, 1, 1, offset_hours, 0, 0),
        open=100.0,
        high=105.0,
        low=95.0,
        close=102.0,
        volume=10000.0,
    )


def test_insert_candle(db):
    candle = _make_candle()
    result = upsert_candle(db, candle)
    assert result is not None
    assert result.symbol == "TEST"
    assert result.timeframe == "1h"


def test_duplicate_candle_skipped(db):
    candle = _make_candle()
    first = upsert_candle(db, candle)
    second = upsert_candle(db, candle)  # same timestamp - should be skipped
    assert first is not None
    assert second is None  # duplicate


def test_get_candles_returns_ordered(db):
    for i in range(5):
        upsert_candle(db, _make_candle(offset_hours=i))

    candles = get_candles(db, symbol="TEST", timeframe="1h")
    assert len(candles) == 5
    # Verify ascending order
    for i in range(1, len(candles)):
        assert candles[i].timestamp_utc > candles[i - 1].timestamp_utc


def test_candle_count(db):
    for i in range(3):
        upsert_candle(db, _make_candle(offset_hours=i))
    assert get_candle_count(db, "TEST", "1h") == 3


# ---------------------------------------------------------------------------
# bulk_upsert_candles — single-transaction batch insert (bug fix tests)
# ---------------------------------------------------------------------------

def test_bulk_upsert_inserts_all_new_candles(db):
    """bulk_upsert_candles must insert every candle when there are no duplicates."""
    candles = [_make_candle(offset_hours=i) for i in range(5)]
    inserted = bulk_upsert_candles(db, candles)
    assert inserted == 5
    assert get_candle_count(db, "TEST", "1h") == 5


def test_bulk_upsert_skips_duplicates(db):
    """Duplicate candles in the batch must be silently skipped without aborting the batch."""
    candles = [_make_candle(offset_hours=i) for i in range(3)]
    first = bulk_upsert_candles(db, candles)
    assert first == 3

    # Re-insert the same 3 candles — all should be skipped
    second = bulk_upsert_candles(db, candles)
    assert second == 0
    assert get_candle_count(db, "TEST", "1h") == 3  # count unchanged


def test_bulk_upsert_partial_duplicates(db):
    """When some candles are new and some are duplicates, only new ones count."""
    candles_first = [_make_candle(offset_hours=i) for i in range(3)]
    bulk_upsert_candles(db, candles_first)

    # 2 overlap with the first batch, 2 are new
    candles_second = [_make_candle(offset_hours=i) for i in range(1, 5)]
    inserted = bulk_upsert_candles(db, candles_second)
    assert inserted == 2
    assert get_candle_count(db, "TEST", "1h") == 5


def test_bulk_upsert_single_commit(db):
    """
    bulk_upsert_candles must use exactly ONE db.commit() for the whole batch,
    not one per candle.  A batch of N candles with the old approach triggered N
    round-trips; the savepoint approach commits once.

    We verify this by patching db.commit and counting calls.
    """
    candles = [_make_candle(offset_hours=i) for i in range(10)]

    commit_calls = []
    original_commit = db.commit

    def counting_commit():
        commit_calls.append(1)
        return original_commit()

    with patch.object(db, "commit", side_effect=counting_commit):
        bulk_upsert_candles(db, candles)

    assert len(commit_calls) == 1, (
        f"Expected 1 commit for a batch of 10 candles, got {len(commit_calls)}. "
        "bulk_upsert_candles must not commit per-row."
    )


def test_bulk_upsert_empty_list(db):
    """Empty input must return 0 without touching the database."""
    inserted = bulk_upsert_candles(db, [])
    assert inserted == 0


def test_bulk_upsert_returns_correct_count(db):
    """Return value must equal the number of rows actually inserted."""
    candles = [_make_candle(offset_hours=i) for i in range(4)]
    # Pre-insert one to create a guaranteed duplicate
    upsert_candle(db, candles[0])

    inserted = bulk_upsert_candles(db, candles)
    assert inserted == 3  # 4 total − 1 duplicate
