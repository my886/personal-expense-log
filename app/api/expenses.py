from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Expense, RecurringExpense
from app.schemas import ExpenseCreate, ExpenseOut, ExpenseUpdate
from app.services.fx import apply_fx, implied_rate
from app.services.recurring import link

router = APIRouter(prefix="/expenses", tags=["expenses"])


def _to_out(expense: Expense) -> ExpenseOut:
    return ExpenseOut(
        id=expense.id,
        amount=expense.amount,
        currency=expense.currency,
        base_amount=expense.base_amount,
        fx_rate=expense.fx_rate,
        date=expense.date,
        category_id=expense.category_id,
        category_name=expense.category.name if expense.category else None,
        vendor=expense.vendor,
        payment_method=expense.payment_method,
        location=expense.location,
        tags=expense.tags,
        notes=expense.notes,
        raw_text=expense.raw_text,
        receipt_image_path=expense.receipt_image_path,
        source=expense.source,
        recurring_id=expense.recurring_id,
        is_fixed=expense.is_fixed,
        created_at=expense.created_at,
    )


async def _apply_recurring(db: AsyncSession, expense: Expense, auto_match: bool) -> None:
    """Validate/auto-link the recurring template; one live linked expense per template per month."""
    # no autoflush: flushing the pending link first would hit the FK / unique index as a 500
    with db.no_autoflush:
        if expense.recurring_id is not None and not await db.get(RecurringExpense, expense.recurring_id):
            raise HTTPException(status_code=404, detail="Recurring expense not found")
        await link(db, expense, auto_match)
        if expense.recurring_id is None:
            return
        stmt = select(Expense.id).where(
            Expense.recurring_id == expense.recurring_id,
            Expense.recurring_month == expense.recurring_month,
            Expense.deleted_at.is_(None),
        )
        if expense.id is not None:
            stmt = stmt.where(Expense.id != expense.id)
        clash = await db.scalar(stmt)
    if clash:
        raise HTTPException(
            status_code=409,
            detail=f"Recurring expense already logged for {expense.recurring_month:%Y-%m} (expense #{clash})",
        )


@router.get("", response_model=list[ExpenseOut])
async def list_expenses(
    month: str | None = Query(default=None, description="YYYY-MM filter"),
    date_filter: date | None = Query(default=None, alias="date", description="Exact date filter"),
    category_id: int | None = Query(default=None),
    include_deleted: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Expense).options(selectinload(Expense.category)).order_by(Expense.date.desc())
    if not include_deleted:
        stmt = stmt.where(Expense.deleted_at.is_(None))
    if month:
        try:
            year, mo = map(int, month.split("-"))
        except ValueError:
            raise HTTPException(status_code=400, detail="month must be YYYY-MM")
        start = date(year, mo, 1)
        if mo == 12:
            end = date(year + 1, 1, 1)
        else:
            end = date(year, mo + 1, 1)
        stmt = stmt.where(Expense.date >= start, Expense.date < end)
    if date_filter:
        stmt = stmt.where(Expense.date == date_filter)
    if category_id is not None:
        stmt = stmt.where(Expense.category_id == category_id)
    result = await db.execute(stmt)
    return [_to_out(e) for e in result.scalars().all()]


@router.post("", response_model=ExpenseOut, status_code=201)
async def create_expense(body: ExpenseCreate, db: AsyncSession = Depends(get_db)):
    data = body.model_dump()
    data["currency"] = data["currency"].upper()
    expense = Expense(**data)

    # A supplied base_amount is the actual SGD debit — keep it and record the implied rate.
    # Otherwise convert at the rate for the expense date.
    if expense.base_amount is not None:
        expense.fx_rate = implied_rate(expense.amount, expense.base_amount)
    else:
        await apply_fx(db, expense)
    await _apply_recurring(db, expense, auto_match=True)

    db.add(expense)
    await db.commit()
    await db.refresh(expense)
    result = await db.execute(
        select(Expense).options(selectinload(Expense.category)).where(Expense.id == expense.id)
    )
    return _to_out(result.scalar_one())


@router.get("/{expense_id}", response_model=ExpenseOut)
async def get_expense(
    expense_id: int,
    include_deleted: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Expense).options(selectinload(Expense.category)).where(Expense.id == expense_id)
    if not include_deleted:
        stmt = stmt.where(Expense.deleted_at.is_(None))
    result = await db.execute(stmt)
    expense = result.scalar_one_or_none()
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    return _to_out(expense)


@router.put("/{expense_id}", response_model=ExpenseOut)
async def update_expense(expense_id: int, body: ExpenseUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Expense).options(selectinload(Expense.category)).where(
            Expense.id == expense_id,
            Expense.deleted_at.is_(None),
        )
    )
    expense = result.scalar_one_or_none()
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    updates = body.model_dump(exclude_unset=True)
    if updates.get("currency"):
        updates["currency"] = updates["currency"].upper()
    for field, value in updates.items():
        setattr(expense, field, value)

    # Recalculate base_amount if currency, amount or date changed (rate depends on date)
    if updates.get("base_amount") is not None:
        expense.fx_rate = implied_rate(expense.amount, expense.base_amount)
    elif updates.keys() & {"currency", "amount", "date", "base_amount"}:
        await apply_fx(db, expense)
    if updates.keys() & {"recurring_id", "date"}:
        await _apply_recurring(db, expense, auto_match=False)

    await db.commit()
    await db.refresh(expense)
    result = await db.execute(
        select(Expense).options(selectinload(Expense.category)).where(Expense.id == expense_id)
    )
    return _to_out(result.scalar_one())


@router.delete("/{expense_id}", status_code=204)
async def delete_expense(
    expense_id: int,
    permanent: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Expense).where(Expense.id == expense_id)
    )
    expense = result.scalar_one_or_none()
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    if permanent:
        await db.delete(expense)
    else:
        expense.deleted_at = datetime.now(tz=timezone.utc)
    await db.commit()
