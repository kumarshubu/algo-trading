"""
Tests for database session lifecycle: rollback-on-exception, commit-on-success.

Root cause: get_db() previously had no rollback in its finally block.
Failed requests left dirty sessions; subsequent queries inside the same
session (or after close) could hit PendingRollbackError or silently
persist partial writes.

Production impact:
- A route that raises after a partial write (e.g. portfolio deducted but
  trade not recorded) could leave the portfolio and trades out of sync.
- Worse, if SQLAlchemy's connection pool reused the dirty session the next
  request could see stale/uncommitted state.

What was changed:
  get_db() now has try/except/finally:
    yield → commit on success
    except → rollback and re-raise
    finally → always close

Why it's safer:
  Rollback is idempotent and cheap; it guarantees that any uncommitted
  changes introduced by a failing request are always discarded.
"""

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.watchlist import Watchlist
from app.models.signal import Signal
from datetime import datetime


# ---------------------------------------------------------------------------
# Rollback mechanism (SQLAlchemy invariant that get_db() relies on)
# ---------------------------------------------------------------------------

def test_rollback_discards_unflushed_add(db):
    """
    A db.add() followed by db.rollback() (no flush/commit) must leave the
    table empty — the object was never written to the database.
    """
    db.add(Watchlist(symbol="ROLLBACK_TEST"))
    db.rollback()

    count = db.query(Watchlist).filter(Watchlist.symbol == "ROLLBACK_TEST").count()
    assert count == 0


def test_rollback_discards_flushed_but_uncommitted_add(db):
    """
    A db.flush() writes to the DB within the current transaction but does NOT
    commit.  A subsequent rollback must undo the flush.
    This is the exact scenario that would occur if a route raised after a
    flush-without-commit: get_db()'s except block calls db.rollback().
    """
    db.add(Watchlist(symbol="FLUSHED_ROLLBACK"))
    db.flush()

    # The row is visible within this session before rollback
    count_before = db.query(Watchlist).filter(Watchlist.symbol == "FLUSHED_ROLLBACK").count()
    assert count_before == 1

    db.rollback()

    count_after = db.query(Watchlist).filter(Watchlist.symbol == "FLUSHED_ROLLBACK").count()
    assert count_after == 0


def test_committed_write_survives_later_rollback(db):
    """
    A row that was committed before the rollback must NOT be undone.
    In the context of get_db(): if a route calls db.commit() partway through
    and then raises, the committed portion is preserved (rollback only undoes
    the uncommitted remainder).
    """
    db.add(Watchlist(symbol="COMMITTED"))
    db.commit()

    # Now add another row without committing, then rollback
    db.add(Watchlist(symbol="NOT_COMMITTED"))
    db.rollback()

    assert db.query(Watchlist).filter(Watchlist.symbol == "COMMITTED").count() == 1
    assert db.query(Watchlist).filter(Watchlist.symbol == "NOT_COMMITTED").count() == 0


# ---------------------------------------------------------------------------
# Savepoint (nested transaction) — used by bulk_upsert_candles
# ---------------------------------------------------------------------------

def test_savepoint_isolates_integrity_error(db):
    """
    A nested transaction (SAVEPOINT) must roll back only the failed insert,
    leaving earlier inserts in the same outer transaction intact.
    This is the mechanism bulk_upsert_candles relies on.
    """
    # Insert first watchlist item
    db.add(Watchlist(symbol="FIRST"))
    db.flush()

    # Try to insert a duplicate inside a savepoint — should fail silently
    try:
        with db.begin_nested():          # SAVEPOINT
            db.add(Watchlist(symbol="FIRST"))  # duplicate → IntegrityError
            db.flush()
    except IntegrityError:
        pass  # savepoint auto-rolled back; outer transaction continues

    # Add a second distinct item — must succeed
    db.add(Watchlist(symbol="SECOND"))
    db.flush()

    db.commit()

    symbols = {w.symbol for w in db.query(Watchlist).all()}
    assert "FIRST" in symbols
    assert "SECOND" in symbols
    assert len(symbols) == 2  # no phantom duplicates


# ---------------------------------------------------------------------------
# get_db() via HTTP endpoint — integration-level rollback test
# ---------------------------------------------------------------------------

def test_api_rollback_on_http_error(client, db):
    """
    When a route raises an HTTPException (e.g. 404), get_db() must not leave
    any uncommitted state behind.  We verify this indirectly: calling an
    endpoint that returns 404 does not corrupt the session for subsequent calls.
    """
    # Signal that definitely doesn't exist
    response = client.post("/api/v1/paper-trades/execute/99999")
    assert response.status_code == 404  # signal not found → 404

    # A subsequent read must still work (session is clean)
    portfolio_resp = client.get("/api/v1/portfolio")
    assert portfolio_resp.status_code == 200
    assert portfolio_resp.json()["success"] is True


def test_session_usable_after_rollback(db):
    """
    After a rollback, the session must accept new operations normally.
    (Verifies we don't leave the session in a broken state.)
    """
    db.add(Watchlist(symbol="PRE_ERROR"))
    db.flush()
    db.rollback()

    # Session should be usable immediately after rollback
    db.add(Watchlist(symbol="POST_ERROR"))
    db.commit()

    result = db.query(Watchlist).filter(Watchlist.symbol == "POST_ERROR").first()
    assert result is not None
    assert result.symbol == "POST_ERROR"
