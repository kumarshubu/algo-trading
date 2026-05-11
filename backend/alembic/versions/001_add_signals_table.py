"""Add signals table

Revision ID: 001
Revises:
Create Date: 2026-05-11

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "signals",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("timeframe", sa.String(10), nullable=False),
        sa.Column("strategy_name", sa.String(100), nullable=False),
        sa.Column("signal_type", sa.String(10), nullable=False),
        sa.Column("candle_timestamp", sa.DateTime, nullable=False),
        sa.Column("generated_at", sa.DateTime, nullable=False),
        sa.Column("metadata_json", sa.Text, nullable=True),
    )
    op.create_index("ix_signals_symbol", "signals", ["symbol"])
    op.create_unique_constraint(
        "uq_signal_symbol_tf_strategy_ts",
        "signals",
        ["symbol", "timeframe", "strategy_name", "candle_timestamp"],
    )


def downgrade() -> None:
    op.drop_table("signals")
