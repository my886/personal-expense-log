from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Expense
from app.schemas import ExpenseCreate, ExpenseOut, ExpenseUpdate

router = APIRouter(prefix="/expenses", tags=["expenses"])


def _to_out(expense: Expense) -> ExpenseOut:
    return ExpenseOut(
        id=expense.id,
        amount=expense.amount,
        currency=expense.currency,
        date=expense.date,
        category_id=expense.category_id,
        category_name=expense.category.name if expense.category else None,
        vendor=expense.vendor,
        notes=expense.notes,
        raw_text=expense.raw_text,
        receipt_image_path=expense.receipt_image_path,
        source=expense.source,
        created_at=expense.created_at,
    )


@router.get("", response_model=list[ExpenseOut])
async def list_expenses(
    month: str | None = Query(default=None, description="YYYY-MM filter"),
    category_id: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Expense).options(selectinload(Expense.category)).order_by(Expense.date.desc())
    if month:
        try:
            year, mo = map(int, month.split("-"))
        except ValueError:
            raise HTTPException(status_code=400, detail="month must be YYYY-MM")
        start = date(year, mo, 1)
        # last day of month: first day of next month minus one day
        if mo == 12:
            end = date(year + 1, 1, 1)
        else:
            end = date(year, mo + 1, 1)
        stmt = stmt.where(Expense.date >= start, Expense.date < end)
    if category_id is not None:
        stmt = stmt.where(Expense.category_id == category_id)
    result = await db.execute(stmt)
    return [_to_out(e) for e in result.scalars().all()]


@router.post("", response_model=ExpenseOut, status_code=201)
async def create_expense(body: ExpenseCreate, db: AsyncSession = Depends(get_db)):
    expense = Expense(**body.model_dump())
    db.add(expense)
    await db.commit()
    await db.refresh(expense)
    # reload with category relationship
    result = await db.execute(
        select(Expense).options(selectinload(Expense.category)).where(Expense.id == expense.id)
    )
    return _to_out(result.scalar_one())


@router.get("/{expense_id}", response_model=ExpenseOut)
async def get_expense(expense_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Expense).options(selectinload(Expense.category)).where(Expense.id == expense_id)
    )
    expense = result.scalar_one_or_none()
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    return _to_out(expense)


@router.put("/{expense_id}", response_model=ExpenseOut)
async def update_expense(expense_id: int, body: ExpenseUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Expense).options(selectinload(Expense.category)).where(Expense.id == expense_id)
    )
    expense = result.scalar_one_or_none()
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(expense, field, value)
    await db.commit()
    await db.refresh(expense)
    result = await db.execute(
        select(Expense).options(selectinload(Expense.category)).where(Expense.id == expense_id)
    )
    return _to_out(result.scalar_one())


@router.delete("/{expense_id}", status_code=204)
async def delete_expense(expense_id: int, db: AsyncSession = Depends(get_db)):
    expense = await db.get(Expense, expense_id)
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    await db.delete(expense)
    await db.commit()
