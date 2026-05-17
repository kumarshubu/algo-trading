"""
SQLAlchemy database setup.
Uses PostgreSQL (Supabase) via DATABASE_URL environment variable.
"""

import os
import sys

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv()

DATABASE_URL: str = os.getenv("DATABASE_URL", "")

if not DATABASE_URL:
    print("FATAL: DATABASE_URL is not set.", file=sys.stderr)
    sys.exit(1)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    connect_args={"prepare_threshold": None},  # disable psycopg3 server-side prepared statements
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def check_db_connection() -> None:
    """Execute SELECT 1; raises on failure."""
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
