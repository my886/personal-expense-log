from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Expense, ExchangeRate
from app.schemas import ExpenseCreate, ExpenseOut, ExpenseUpdate

router = APIRouter(prefix="/expenses", tags=["expenses"])


def _to_out(expense: Expense) -> ExpenseOut:
    return ExpenseOut(
        id=expense.id,
        amount=expense.amount,
        currency=expense.currency,
        base_amount=expense.base_amount,
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
        created_at=expense.created_at,
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
    currency = data.get("currency", "SGD")

    # Auto-calculate base_amount if not provided and currency != SGD
    if currency != "SGD" and data.get("base_amount") is None:
        rate_result = await db.execute(
            select(ExchangeRate).where(ExchangeRate.target_currency == currency)
        )
        rate_obj = rate_result.scalar_one_or_none()
        if rate_obj:
            base = float(data["amount"]) * float(rate_obj.rate)
            data["base_amount"] = round(base, 2)
    elif currency == "SGD" and data.get("base_amount") is None:
        data["base_amount"] = data["amount"]

    expense = Expense(**data)
    db.add(expense)
    await db.commit()
    await db.refresh(expense)
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
        expense.deleted_at = datetime.now(expense.deleted_at.tzinfo) if expense.deleted_at else datetime.utcnow()
    await db.commit()
