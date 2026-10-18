"""Backfill expenses.fx_rate / base_amount using historical rates for each expense date.

- SGD rows: fx_rate = 1, base_amount = amount
- Non-SGD rows with no base_amount, or one auto-computed at the old flat MYR 0.33 rate:
  recompute at the rate for the expense date
- Non-SGD rows with any other base_amount (user-supplied actual debit): keep it, record implied rate

Also removes the old flat 'manual' MYR 0.33 placeholder rate so it can't be reused.

Usage: uv run python -m scripts.backfill_fx [--apply]
"""
import asyncio
import sys
from decimal import Decimal

from sqlalchemy import delete, select

from app.database import SessionLocal
from app.models import ExchangeRate, Expense
from app.services.fx import BASE_CURRENCY, get_rate, implied_rate, to_base

STALE_MYR_RATE = Decimal("0.33")


async def main(apply: bool) -> None:
    async with SessionLocal() as db:
        await db.execute(
            delete(ExchangeRate).where(
                ExchangeRate.target_currency == "MYR",
                ExchangeRate.rate == STALE_MYR_RATE,
                ExchangeRate.source == "manual",
            )
        )

        expenses = (await db.execute(select(Expense).order_by(Expense.date))).scalars().all()
        old_total = new_total = Decimal("0")
        changed = 0
        for e in expenses:
            old_base, old_fx = e.base_amount, e.fx_rate
            if e.currency == BASE_CURRENCY:
                e.fx_rate = Decimal("1")
                e.base_amount = e.amount
            elif e.base_amount is None or (
                e.currency == "MYR" and e.base_amount == to_base(e.amount, STALE_MYR_RATE)
            ):
                rate = await get_rate(db, e.currency, e.date)
                e.fx_rate = rate
                e.base_amount = to_base(e.amount, rate) if rate is not None else None
            else:
                e.fx_rate = implied_rate(e.amount, e.base_amount)

            if (old_base, old_fx) != (e.base_amount, e.fx_rate):
                changed += 1
            if e.deleted_at is None:
                old_total += old_base if old_base is not None else e.amount  # analytics' coalesce fallback
                new_total += e.base_amount if e.base_amount is not None else e.amount
            if e.currency != BASE_CURRENCY or old_base is None:
                print(f"#{e.id:<4} {e.date} {e.amount:>9} {e.currency}  base {old_base} -> {e.base_amount}  fx {e.fx_rate}")

        print(f"\n{changed} rows changed. Non-deleted total (SGD): {old_total} -> {new_total} ({new_total - old_total:+})")
        if apply:
            await db.commit()
            print("Applied.")
        else:
            await db.rollback()
            print("Dry run — rerun with --apply to save.")


if __name__ == "__main__":
    asyncio.run(main("--apply" in sys.argv))
