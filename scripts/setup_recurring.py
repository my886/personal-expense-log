"""One-off setup: Family category, recurring templates, and linking of past fixed costs.

Idempotent. Usage: uv run python -m scripts.setup_recurring [--apply]
"""
import asyncio
import sys
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Category, Expense, RecurringExpense
from app.services.recurring import find_match, month_start

FAMILY_PATTERN = r"family|remittance|maintenance"

# (name, amount, currency, category, match, day, auto_create, payment_method)
TEMPLATES = [
    ("Family maintenance", "1600.00", "MYR", "Family", FAMILY_PATTERN, 1, True, "online"),
    ("Zero1 mobile", "7.06", "SGD", "Utilities", r"zero1", 8, False, "card"),
    ("Rent", "540.00", "SGD", "Rent", r"rent", 28, True, None),
    ("MRT monthly", "75.00", "SGD", "Transport", r"monthly.*(mrt|pass|bill)|mrt.*monthly", 28, False, "card"),
    ("Circles.Life mobile", "8.70", "SGD", "Utilities", r"circles", 30, False, "card"),
    ("Unifi broadband (MY)", "95.00", "MYR", "Utilities", r"unifi|broadband", 30, False, "online"),
]
START_MONTH = date(2026, 8, 1)  # first month fixed costs were logged


async def main(apply: bool) -> None:
    async with SessionLocal() as db:
        cats = {c.name: c for c in (await db.execute(select(Category))).scalars().all()}
        if "Family" not in cats:
            cats["Family"] = Category(name="Family", is_default=False)
            db.add(cats["Family"])
            await db.flush()
            print("Created category Family")

        others = cats["Others"].id
        refile = (
            await db.execute(
                select(Expense).where(
                    Expense.category_id == others,
                    Expense.deleted_at.is_(None),
                    (Expense.notes.op("~*")(FAMILY_PATTERN)) | (Expense.vendor.op("~*")(FAMILY_PATTERN)),
                )
            )
        ).scalars().all()
        for e in refile:
            e.category_id = cats["Family"].id
            print(f"Refiled #{e.id} {e.date} {e.amount} {e.currency} Others -> Family: {e.notes}")

        for name, amount, currency, cat, match, day, auto, pm in TEMPLATES:
            if await db.scalar(select(RecurringExpense).where(RecurringExpense.name == name)):
                continue
            db.add(RecurringExpense(
                name=name, amount=Decimal(amount), currency=currency, category_id=cats[cat].id,
                match=match, day_of_month=day, auto_create=auto, payment_method=pm, start_month=START_MONTH,
            ))
            print(f"Template: {name} — {amount} {currency}, day {day}, {'auto-create' if auto else 'expected only'}")
        await db.flush()

        candidates = (
            await db.execute(
                select(Expense)
                .where(Expense.recurring_id.is_(None), Expense.deleted_at.is_(None), Expense.date >= START_MONTH)
                .order_by(Expense.date, Expense.id)
            )
        ).scalars().all()
        for e in candidates:
            template = await find_match(db, e)
            if template:
                e.recurring_id, e.recurring_month = template.id, month_start(e.date)
                await db.flush()
                print(f"Linked #{e.id} {e.date} {e.amount:>8} {e.currency} -> {template.name}  ({e.vendor or ''} / {(e.notes or '')[:40]})")

        if apply:
            await db.commit()
            print("Applied.")
        else:
            await db.rollback()
            print("Dry run — rerun with --apply to save.")


if __name__ == "__main__":
    asyncio.run(main("--apply" in sys.argv))
