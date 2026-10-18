"""
Recurring (fixed) monthly costs.

An expense linked to a recurring template is a fixed cost; everything else is variable.
Links are made explicitly (recurring_id on create/update), by auto-match on create
(same category + template.match regex on vendor/notes), or by run_due() creating the
expense for auto_create templates on their due day. At most one linked expense per
template per month among non-deleted expenses (uq_expense_recurring_month).
"""
import calendar
import logging
import re
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Expense, RecurringExpense
from app.services.fx import apply_fx

logger = logging.getLogger(__name__)


def month_start(d: date) -> date:
    return d.replace(day=1)


def due_date(template: RecurringExpense, month: date) -> date:
    last_day = calendar.monthrange(month.year, month.month)[1]
    return month.replace(day=min(template.day_of_month, last_day))


def _in_effect(template: RecurringExpense, month: date) -> bool:
    return template.active and template.start_month <= month and (
        template.end_month is None or month <= template.end_month
    )


async def _linked_expense(db: AsyncSession, template_id: int, month: date, include_deleted: bool = False) -> Expense | None:
    stmt = select(Expense).where(Expense.recurring_id == template_id, Expense.recurring_month == month)
    if not include_deleted:
        stmt = stmt.where(Expense.deleted_at.is_(None))
    return await db.scalar(stmt.limit(1))


async def find_match(db: AsyncSession, expense: Expense) -> RecurringExpense | None:
    """Template this expense looks like, if that template has nothing linked this month yet."""
    if expense.category_id is None:
        return None
    month = month_start(expense.date)
    templates = (
        await db.execute(
            select(RecurringExpense).where(
                RecurringExpense.category_id == expense.category_id,
                RecurringExpense.match.is_not(None),
            )
        )
    ).scalars().all()
    text = f"{expense.vendor or ''}\n{expense.notes or ''}"
    for t in templates:
        if _in_effect(t, month) and re.search(t.match, text, re.IGNORECASE):
            if await _linked_expense(db, t.id, month) is None:
                return t
    return None


async def link(db: AsyncSession, expense: Expense, auto_match: bool) -> None:
    """Set recurring_month for a linked expense, or auto-link it to a matching template."""
    if expense.recurring_id is None and auto_match:
        template = await find_match(db, expense)
        if template:
            expense.recurring_id = template.id
            logger.info("Auto-linked expense to recurring '%s'", template.name)
    expense.recurring_month = month_start(expense.date) if expense.recurring_id else None


async def run_due(db: AsyncSession, today: date) -> list[Expense]:
    """Create this month's expense for each auto_create template that is due and not yet logged."""
    month = month_start(today)
    templates = (
        await db.execute(select(RecurringExpense).where(RecurringExpense.auto_create.is_(True)))
    ).scalars().all()
    created = []
    for t in templates:
        if not _in_effect(t, month) or due_date(t, month) > today:
            continue
        # a deleted linked expense means the user dismissed this month — don't recreate it
        if await _linked_expense(db, t.id, month, include_deleted=True):
            continue
        expense = Expense(
            amount=t.amount,
            currency=t.currency,
            date=due_date(t, month),
            category_id=t.category_id,
            vendor=t.vendor,
            payment_method=t.payment_method,
            notes=t.notes or t.name,
            source="recurring",
            recurring_id=t.id,
            recurring_month=month,
        )
        await apply_fx(db, expense)
        db.add(expense)
        created.append(expense)
    return created
