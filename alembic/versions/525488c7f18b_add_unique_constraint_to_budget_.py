"""add unique constraint to budget category_month

Revision ID: 525488c7f18b
Revises: dd71577f8a17
Create Date: 2026-04-16 21:20:40.541572

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '525488c7f18b'
down_revision: Union[str, Sequence[str], None] = 'dd71577f8a17'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_unique_constraint('uq_budget_category_month', 'budgets', ['category_id', 'month'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('uq_budget_category_month', 'budgets', type_='unique')
