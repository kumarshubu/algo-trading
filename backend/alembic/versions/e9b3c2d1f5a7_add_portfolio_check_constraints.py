"""add_portfolio_check_constraints

Revision ID: e9b3c2d1f5a7
Revises: c7f4a1b2d8e3
Create Date: 2026-05-11 13:00:00.000000

"""
from typing import Sequence, Union
from alembic import op

revision: str = 'e9b3c2d1f5a7'
down_revision: Union[str, None] = 'c7f4a1b2d8e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_portfolio_virtual_balance_non_negative",
        "paper_portfolio",
        "virtual_balance >= 0",
    )
    op.create_check_constraint(
        "ck_portfolio_daily_loss_non_negative",
        "paper_portfolio",
        "daily_loss >= 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_portfolio_daily_loss_non_negative",      "paper_portfolio")
    op.drop_constraint("ck_portfolio_virtual_balance_non_negative", "paper_portfolio")
