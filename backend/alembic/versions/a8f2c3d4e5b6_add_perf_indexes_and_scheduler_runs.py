"""add_perf_indexes_and_scheduler_runs

Adds composite/status indexes on hot query paths and a scheduler_runs
audit table so Monday's cycles can be inspected if anything goes wrong.

Hot paths covered:
  - candles(symbol, timeframe)     — every get_candles / get_next_candle call
  - pending_executions(status)     — PENDING poll every intraday cycle
  - paper_trades(symbol, status)   — close-all-open-trades + stop-loss checks

Revision ID: a8f2c3d4e5b6
Revises: e9b3c2d1f5a7
Create Date: 2026-05-17 00:00:00.000000
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'a8f2c3d4e5b6'
down_revision: Union[str, None] = 'e9b3c2d1f5a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Composite index: every candle query filters on (symbol, timeframe)
    op.create_index('ix_candles_symbol_timeframe', 'candles', ['symbol', 'timeframe'])

    # Status index: pending execution poll filters status == 'PENDING' every cycle
    op.create_index('ix_pending_executions_status', 'pending_executions', ['status'])

    # Composite: close-all-open-trades query filters (symbol, status) + orders by created_at
    op.create_index('ix_paper_trades_symbol_status', 'paper_trades', ['symbol', 'status'])

    # Scheduler run audit table
    op.create_table(
        'scheduler_runs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('job_id', sa.String(length=50), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('symbols_processed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('candles_inserted', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('signals_generated', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('pending_executed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('errors', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error_detail', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_scheduler_runs_job_id', 'scheduler_runs', ['job_id'])
    op.create_index('ix_scheduler_runs_started_at', 'scheduler_runs', ['started_at'])


def downgrade() -> None:
    op.drop_index('ix_scheduler_runs_started_at', table_name='scheduler_runs')
    op.drop_index('ix_scheduler_runs_job_id', table_name='scheduler_runs')
    op.drop_table('scheduler_runs')
    op.drop_index('ix_paper_trades_symbol_status', table_name='paper_trades')
    op.drop_index('ix_pending_executions_status', table_name='pending_executions')
    op.drop_index('ix_candles_symbol_timeframe', table_name='candles')
