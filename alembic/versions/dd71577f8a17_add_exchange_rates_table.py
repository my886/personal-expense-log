"""add exchange_rates table

Revision ID: dd71577f8a17
Revises: 6f054c84c715
Create Date: 2026-04-15 22:29:08.568894

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'dd71577f8a17'
down_revision: Union[str, Sequence[str], None] = '6f054c84c715'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('exchange_rates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('target_currency', sa.String(length=3), nullable=False),
        sa.Column('rate', sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('target_currency')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('exchange_rates')
