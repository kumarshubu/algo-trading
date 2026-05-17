"""Alembic migration environment."""

import os
import sys
from logging.config import fileConfig

from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool
from alembic import context

# Add backend directory to path so app imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

load_dotenv()

# Import ALL models so Alembic autogenerate can see the full schema.
# Missing imports here = missing tables in generated migrations.
from app.db.database import Base
from app.models import (  # noqa: F401
    candle,
    trade,
    position,
    watchlist,
    strategy,
    portfolio,
    signal,
    equity_snapshot,
    pending_execution,
    scheduler_run,
    execution_event,
)

config = context.config
fileConfig(config.config_file_name)

# Override sqlalchemy.url with DATABASE_URL from .env
database_url = os.getenv("DATABASE_URL")
if not database_url:
    raise RuntimeError("DATABASE_URL is not set")
config.set_main_option("sqlalchemy.url", database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Render items in a deterministic order
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
