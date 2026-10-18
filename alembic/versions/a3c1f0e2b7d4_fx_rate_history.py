"""exchange rate history + per-expense fx_rate

Revision ID: a3c1f0e2b7d4
Revises: 525488c7f18b
Create Date: 2026-10-18 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a3c1f0e2b7d4'
down_revision: Union[str, Sequence[str], None] = '525488c7f18b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # exchange_rates: one row per currency -> one row per (currency, date)
    op.add_column('exchange_rates', sa.Column('rate_date', sa.Date(), nullable=True))
    op.add_column('exchange_rates', sa.Column('source', sa.String(length=10), server_default='manual', nullable=False))
    op.execute("UPDATE exchange_rates SET rate_date = (updated_at AT TIME ZONE 'Asia/Singapore')::date")
    op.alter_column('exchange_rates', 'rate_date', nullable=False)
    op.drop_constraint('exchange_rates_target_currency_key', 'exchange_rates', type_='unique')
    op.create_unique_constraint('uq_exchange_rate_currency_date', 'exchange_rates', ['target_currency', 'rate_date'])

    # expenses: snapshot of the rate used to compute base_amount
    op.add_column('expenses', sa.Column('fx_rate', sa.Numeric(precision=12, scale=6), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('expenses', 'fx_rate')
    # keep only the latest row per currency so the old unique constraint can be restored
    op.execute("""
        DELETE FROM exchange_rates e USING exchange_rates newer
        WHERE e.target_currency = newer.target_currency AND e.rate_date < newer.rate_date
    """)
    op.drop_constraint('uq_exchange_rate_currency_date', 'exchange_rates', type_='unique')
    op.create_unique_constraint('exchange_rates_target_currency_key', 'exchange_rates', ['target_currency'])
    op.drop_column('exchange_rates', 'source')
    op.drop_column('exchange_rates', 'rate_date')
