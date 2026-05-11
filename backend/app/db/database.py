"""
SQLAlchemy database setup.
Uses SQLite with synchronous access - keeps it simple for local dev.
"""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings


# SQLite-specific: enable WAL mode and foreign keys
def _configure_sqlite(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},  # needed for SQLite with FastAPI
    echo=settings.debug,
)

event.listen(engine, "connect", _configure_sqlite)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency for database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
