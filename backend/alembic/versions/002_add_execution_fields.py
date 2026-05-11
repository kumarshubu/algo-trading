"""Add signal_id to paper_trades and equity_snapshots table

Revision ID: 002
Revises: 001
Create Date: 2026-05-11
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add signal_id to paper_trades (nullable — supports both signal-triggered and manual trades)
    op.add_column("paper_trades", sa.Column("signal_id", sa.Integer, nullable=True))
    op.create_index("ix_paper_trades_signal_id", "paper_trades", ["signal_id"])

    op.create_table(
        "equity_snapshots",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("timestamp", sa.DateTime, nullable=False),
        sa.Column("balance", sa.Float, nullable=False),
        sa.Column("unrealized_pnl", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("realized_pnl", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("drawdown", sa.Float, nullable=False, server_default="0.0"),
    )
    op.create_index("ix_equity_snapshots_timestamp", "equity_snapshots", ["timestamp"])


def downgrade() -> None:
    op.drop_index("ix_paper_trades_signal_id", "paper_trades")
    op.drop_column("paper_trades", "signal_id")
    op.drop_table("equity_snapshots")
