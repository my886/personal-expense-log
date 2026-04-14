"""add expense tracking fields and budgets table

Revision ID: 6f054c84c715
Revises: 20260411164516
Create Date: 2026-04-14 23:19:13.928226

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '6f054c84c715'
down_revision: Union[str, Sequence[str], None] = '20260411164516'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create budgets table
    op.create_table('budgets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('category_id', sa.Integer(), nullable=False),
        sa.Column('month', sa.Date(), nullable=False),
        sa.Column('limit_amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    # Add new columns to expenses
    op.add_column('expenses', sa.Column('base_amount', sa.Numeric(precision=10, scale=2), nullable=True))
    op.add_column('expenses', sa.Column('payment_method', sa.String(length=20), nullable=True))
    op.add_column('expenses', sa.Column('location', sa.String(length=255), nullable=True))
    op.add_column('expenses', sa.Column('tags', postgresql.ARRAY(sa.Text()), nullable=True))
    op.add_column('expenses', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema — removes all new columns and budgets table."""
    op.drop_column('expenses', 'deleted_at')
    op.drop_column('expenses', 'tags')
    op.drop_column('expenses', 'location')
    op.drop_column('expenses', 'payment_method')
    op.drop_column('expenses', 'base_amount')
    op.drop_table('budgets')
