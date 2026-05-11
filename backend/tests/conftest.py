"""Pytest fixtures shared across test modules."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.database import Base, get_db

# StaticPool ensures all sessions share the same in-memory DB connection.
# Without it, each new connection gets a fresh empty database.
test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def _configure_sqlite_test(dbapi_conn, connection_record):
    """
    Mirror the production SQLite pragma configuration in the test database.

    Without PRAGMA foreign_keys=ON, SQLite silently ignores FK violations,
    meaning tests would not catch constraint bugs that production would catch.
    WAL mode is skipped because in-memory DBs don't benefit from it.
    """
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


event.listen(test_engine, "connect", _configure_sqlite_test)


@pytest.fixture(scope="function")
def db():
    Base.metadata.create_all(bind=test_engine)
    session = TestSessionLocal()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="function")
def client(db):
    """
    FastAPI TestClient with the DB dependency overridden to use the test
    session.  The override mirrors the rollback-on-exception contract of
    the production get_db() so error-path behaviour is consistent.
    """
    def override_get_db():
        try:
            yield db
        except Exception:
            db.rollback()
            raise

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
