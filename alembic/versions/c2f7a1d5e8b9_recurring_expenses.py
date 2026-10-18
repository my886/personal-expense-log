"""recurring expense templates; expenses linked to them are fixed costs

Revision ID: c2f7a1d5e8b9
Revises: b8e4d2a9c613
Create Date: 2026-10-18 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c2f7a1d5e8b9'
down_revision: Union[str, Sequence[str], None] = 'b8e4d2a9c613'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('recurring_expenses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('amount', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('category_id', sa.Integer(), nullable=False),
        sa.Column('vendor', sa.String(length=255), nullable=True),
        sa.Column('payment_method', sa.String(length=20), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('match', sa.String(length=255), nullable=True),
        sa.Column('day_of_month', sa.Integer(), nullable=False),
        sa.Column('auto_create', sa.Boolean(), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('start_month', sa.Date(), nullable=False),
        sa.Column('end_month', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['category_id'], ['categories.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )
    op.add_column('expenses', sa.Column('recurring_id', sa.Integer(), nullable=True))
    op.add_column('expenses', sa.Column('recurring_month', sa.Date(), nullable=True))
    op.create_foreign_key('fk_expenses_recurring_id', 'expenses', 'recurring_expenses', ['recurring_id'], ['id'])
    # partial: a soft-deleted linked expense must not block re-logging that month
    op.create_index('uq_expense_recurring_month', 'expenses', ['recurring_id', 'recurring_month'],
                    unique=True, postgresql_where=sa.text('deleted_at IS NULL'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_expense_recurring_month', table_name='expenses')
    op.drop_constraint('fk_expenses_recurring_id', 'expenses', type_='foreignkey')
    op.drop_column('expenses', 'recurring_month')
    op.drop_column('expenses', 'recurring_id')
    op.drop_table('recurring_expenses')
