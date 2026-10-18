"""widen fx rate precision and amount range for low-value currencies (VND, IDR, JPY)

Revision ID: b8e4d2a9c613
Revises: a3c1f0e2b7d4
Create Date: 2026-10-18 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b8e4d2a9c613'
down_revision: Union[str, Sequence[str], None] = 'a3c1f0e2b7d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1 VND ≈ 0.0000496 SGD — 6 decimal places keeps only 2 significant figures
    op.alter_column('exchange_rates', 'rate', type_=sa.Numeric(18, 10), existing_nullable=False)
    op.alter_column('expenses', 'fx_rate', type_=sa.Numeric(18, 10), existing_nullable=True)
    # VND/IDR totals can exceed 99,999,999.99
    op.alter_column('expenses', 'amount', type_=sa.Numeric(14, 2), existing_nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column('expenses', 'amount', type_=sa.Numeric(10, 2), existing_nullable=False)
    op.alter_column('expenses', 'fx_rate', type_=sa.Numeric(12, 6), existing_nullable=True)
    op.alter_column('exchange_rates', 'rate', type_=sa.Numeric(12, 6), existing_nullable=False)
