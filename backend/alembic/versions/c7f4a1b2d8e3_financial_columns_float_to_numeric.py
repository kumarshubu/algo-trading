"""financial_columns_float_to_numeric

Revision ID: c7f4a1b2d8e3
Revises: 3d39675bac89
Create Date: 2026-05-11 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'c7f4a1b2d8e3'
down_revision: Union[str, None] = '3d39675bac89'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_MONEY = sa.Numeric(precision=15, scale=4)


def upgrade() -> None:
    op.alter_column('paper_portfolio', 'virtual_balance',    type_=_MONEY, existing_type=sa.Float())
    op.alter_column('paper_portfolio', 'initial_balance',    type_=_MONEY, existing_type=sa.Float())
    op.alter_column('paper_portfolio', 'total_realized_pnl', type_=_MONEY, existing_type=sa.Float())
    op.alter_column('paper_portfolio', 'daily_loss',         type_=_MONEY, existing_type=sa.Float())

    op.alter_column('paper_positions', 'average_price',  type_=_MONEY, existing_type=sa.Float())
    op.alter_column('paper_positions', 'unrealized_pnl', type_=_MONEY, existing_type=sa.Float())

    op.alter_column('paper_trades', 'entry_price',   type_=_MONEY, existing_type=sa.Float())
    op.alter_column('paper_trades', 'exit_price',    type_=_MONEY, existing_type=sa.Float(), existing_nullable=True)
    op.alter_column('paper_trades', 'pnl',           type_=_MONEY, existing_type=sa.Float(), existing_nullable=True)
    op.alter_column('paper_trades', 'stop_loss',     type_=_MONEY, existing_type=sa.Float(), existing_nullable=True)
    op.alter_column('paper_trades', 'target_price',  type_=_MONEY, existing_type=sa.Float(), existing_nullable=True)


def downgrade() -> None:
    op.alter_column('paper_trades', 'target_price',  type_=sa.Float(), existing_type=_MONEY, existing_nullable=True)
    op.alter_column('paper_trades', 'stop_loss',     type_=sa.Float(), existing_type=_MONEY, existing_nullable=True)
    op.alter_column('paper_trades', 'pnl',           type_=sa.Float(), existing_type=_MONEY, existing_nullable=True)
    op.alter_column('paper_trades', 'exit_price',    type_=sa.Float(), existing_type=_MONEY, existing_nullable=True)
    op.alter_column('paper_trades', 'entry_price',   type_=sa.Float(), existing_type=_MONEY)

    op.alter_column('paper_positions', 'unrealized_pnl', type_=sa.Float(), existing_type=_MONEY)
    op.alter_column('paper_positions', 'average_price',  type_=sa.Float(), existing_type=_MONEY)

    op.alter_column('paper_portfolio', 'daily_loss',         type_=sa.Float(), existing_type=_MONEY)
    op.alter_column('paper_portfolio', 'total_realized_pnl', type_=sa.Float(), existing_type=_MONEY)
    op.alter_column('paper_portfolio', 'initial_balance',    type_=sa.Float(), existing_type=_MONEY)
    op.alter_column('paper_portfolio', 'virtual_balance',    type_=sa.Float(), existing_type=_MONEY)
