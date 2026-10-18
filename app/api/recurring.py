from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Category, Expense, RecurringExpense
from app.schemas import ExpenseOut, RecurringCreate, RecurringOut, RecurringStatus, RecurringUpdate
from app.api.expenses import _to_out
from app.services.fx import get_rate, to_base
from app.services.recurring import due_date, month_start, run_due

router = APIRouter(prefix="/recurring", tags=["recurring"])


def _recurring_out(t: RecurringExpense) -> RecurringOut:
    out = RecurringOut.model_validate(t)
    out.category_name = t.category.name if t.category else None
    return out


def _parse_month(month: str | None) -> date:
    if not month:
        return month_start(date.today())
    try:
        year, mo = map(int, month.split("-"))
        return date(year, mo, 1)
    except ValueError:
        raise HTTPException(status_code=400, detail="month must be YYYY-MM")


@router.get("", response_model=list[RecurringOut])
async def list_recurring(
    include_inactive: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(RecurringExpense).options(selectinload(RecurringExpense.category)).order_by(RecurringExpense.day_of_month)
    if not include_inactive:
        stmt = stmt.where(RecurringExpense.active.is_(True))
    result = await db.execute(stmt)
    return [_recurring_out(t) for t in result.scalars().all()]


@router.post("", response_model=RecurringOut, status_code=201)
async def create_recurring(body: RecurringCreate, db: AsyncSession = Depends(get_db)):
    if not await db.get(Category, body.category_id):
        raise HTTPException(status_code=404, detail="Category not found")
    if await db.scalar(select(RecurringExpense).where(RecurringExpense.name == body.name)):
        raise HTTPException(status_code=409, detail="Recurring expense with this name already exists")
    data = body.model_dump()
    data["currency"] = data["currency"].upper()
    data["start_month"] = month_start(data["start_month"] or date.today())
    if data["end_month"]:
        data["end_month"] = month_start(data["end_month"])
    template = RecurringExpense(**data)
    db.add(template)
    await db.commit()
    await db.refresh(template, ["category"])
    return _recurring_out(template)


@router.put("/{recurring_id}", response_model=RecurringOut)
async def update_recurring(recurring_id: int, body: RecurringUpdate, db: AsyncSession = Depends(get_db)):
    template = await db.get(RecurringExpense, recurring_id)
    if not template:
        raise HTTPException(status_code=404, detail="Recurring expense not found")
    updates = body.model_dump(exclude_unset=True)
    if updates.get("category_id") and not await db.get(Category, updates["category_id"]):
        raise HTTPException(status_code=404, detail="Category not found")
    if updates.get("currency"):
        updates["currency"] = updates["currency"].upper()
    for field in ("start_month", "end_month"):
        if updates.get(field):
            updates[field] = month_start(updates[field])
    for field, value in updates.items():
        setattr(template, field, value)
    await db.commit()
    await db.refresh(template, ["category"])
    return _recurring_out(template)


@router.delete("/{recurring_id}", status_code=204)
async def deactivate_recurring(recurring_id: int, db: AsyncSession = Depends(get_db)):
    """Deactivate (not delete): past linked expenses stay fixed costs."""
    template = await db.get(RecurringExpense, recurring_id)
    if not template:
        raise HTTPException(status_code=404, detail="Recurring expense not found")
    template.active = False
    await db.commit()


@router.get("/status", response_model=list[RecurringStatus])
async def recurring_status(
    month: str | None = Query(default=None, description="YYYY-MM, defaults to current month"),
    db: AsyncSession = Depends(get_db),
):
    """Each recurring cost for the month: logged, due (past due date, not logged) or upcoming."""
    start = _parse_month(month)
    templates = (
        await db.execute(
            select(RecurringExpense)
            .options(selectinload(RecurringExpense.category))
            .where(
                RecurringExpense.start_month <= start,
                (RecurringExpense.end_month.is_(None)) | (RecurringExpense.end_month >= start),
            )
            .order_by(RecurringExpense.day_of_month)
        )
    ).scalars().all()
    linked = {
        e.recurring_id: e
        for e in (
            await db.execute(
                select(Expense).where(Expense.recurring_month == start, Expense.deleted_at.is_(None))
            )
        ).scalars().all()
    }
    today = date.today()
    rows = []
    for t in templates:
        expense = linked.get(t.id)
        if not t.active and expense is None:
            continue
        due = due_date(t, start)
        rate = await get_rate(db, t.currency, min(due, today))
        rows.append(RecurringStatus(
            recurring_id=t.id,
            name=t.name,
            category_name=t.category.name if t.category else None,
            due_date=due,
            auto_create=t.auto_create,
            status="logged" if expense else ("due" if due <= today else "upcoming"),
            expected_amount=t.amount,
            currency=t.currency,
            expected_base_amount=to_base(t.amount, rate) if rate is not None else None,
            expense_id=expense.id if expense else None,
            base_amount=expense.base_amount if expense else None,
        ))
    await db.commit()  # persist any rates fetched above
    return rows


@router.post("/run", response_model=list[ExpenseOut])
async def run_recurring(
    on_date: date | None = Query(default=None, alias="date", description="Defaults to today"),
    db: AsyncSession = Depends(get_db),
):
    """Log due auto_create recurring expenses for the month. Idempotent — safe to call daily."""
    created = await run_due(db, on_date or date.today())
    await db.commit()
    if not created:
        return []
    result = await db.execute(
        select(Expense).options(selectinload(Expense.category)).where(Expense.id.in_([e.id for e in created]))
    )
    return [_to_out(e) for e in result.scalars().all()]
