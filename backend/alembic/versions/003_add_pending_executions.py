"""Add pending_executions table

Revision ID: 003
Revises: 002
Create Date: 2026-05-11
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pending_executions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("signal_id", sa.Integer, nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("timeframe", sa.String(10), nullable=False),
        sa.Column("strategy_name", sa.String(100), nullable=False),
        sa.Column("execute_after_timestamp", sa.DateTime, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("cancel_reason", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_pending_executions_signal_id", "pending_executions", ["signal_id"])
    op.create_index("ix_pending_executions_symbol", "pending_executions", ["symbol"])
    op.create_index("ix_pending_executions_status", "pending_executions", ["status"])
    op.create_unique_constraint(
        "uq_pending_execution_signal_id", "pending_executions", ["signal_id"]
    )


def downgrade() -> None:
    op.drop_table("pending_executions")
