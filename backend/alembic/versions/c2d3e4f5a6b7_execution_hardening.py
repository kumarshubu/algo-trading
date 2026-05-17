"""execution_hardening

Adds:
  1. Partial unique index on paper_trades(signal_id) WHERE signal_id IS NOT NULL
     — prevents crash-recovery double-execution of the same signal
  2. execution_events table — structured event log for BUY/SELL/STOP/STALE/DUPLICATE
  3. stale_skips + duplicate_blocks columns on scheduler_runs

Revision ID: c2d3e4f5a6b7
Revises: a8f2c3d4e5b6
Create Date: 2026-05-17 00:01:00.000000
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'c2d3e4f5a6b7'
down_revision: Union[str, None] = 'a8f2c3d4e5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Crash-recovery guard: same signal can only produce one trade, even after restart
    op.create_index(
        'uq_paper_trades_signal_id',
        'paper_trades',
        ['signal_id'],
        unique=True,
        postgresql_where=sa.text('signal_id IS NOT NULL'),
    )

    # Structured execution event log
    op.create_table(
        'execution_events',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('event_type', sa.String(length=50), nullable=False),
        sa.Column('symbol', sa.String(length=20), nullable=True),
        sa.Column('strategy_name', sa.String(length=100), nullable=True),
        sa.Column('cycle_id', sa.String(length=36), nullable=True),
        sa.Column('details_json', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_execution_events_event_type', 'execution_events', ['event_type'])
    op.create_index('ix_execution_events_symbol',     'execution_events', ['symbol'])
    op.create_index('ix_execution_events_created_at', 'execution_events', ['created_at'])
    op.create_index('ix_execution_events_cycle_id',   'execution_events', ['cycle_id'])

    # Richer scheduler-run telemetry
    op.add_column('scheduler_runs', sa.Column('stale_skips',     sa.Integer(), nullable=True, server_default='0'))
    op.add_column('scheduler_runs', sa.Column('duplicate_blocks', sa.Integer(), nullable=True, server_default='0'))


def downgrade() -> None:
    op.drop_column('scheduler_runs', 'duplicate_blocks')
    op.drop_column('scheduler_runs', 'stale_skips')

    op.drop_index('ix_execution_events_cycle_id',   table_name='execution_events')
    op.drop_index('ix_execution_events_created_at', table_name='execution_events')
    op.drop_index('ix_execution_events_symbol',     table_name='execution_events')
    op.drop_index('ix_execution_events_event_type', table_name='execution_events')
    op.drop_table('execution_events')

    op.drop_index('uq_paper_trades_signal_id', table_name='paper_trades')
