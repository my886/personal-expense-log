from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Date, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Budget, Expense, Category
from app.schemas import BudgetCreate, BudgetOut

router = APIRouter(prefix="/budgets", tags=["budgets"])


@router.get("", response_model=list[BudgetOut])
async def list_budgets(
    month: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(
            Budget.id,
            Budget.category_id,
            Category.name.label("category_name"),
            Budget.month,
            Budget.limit_amount,
            Budget.currency,
            Budget.created_at,
            func.coalesce(func.sum(
                func.coalesce(Expense.base_amount, Expense.amount)
            ), 0).label("spent"),
        )
        .outerjoin(Category, Budget.category_id == Category.id)
        .outerjoin(
            Expense,
            (Expense.category_id == Budget.category_id)
            & (Expense.date >= Budget.month)
            & (Expense.date < func.cast(
                func.date_trunc("month", Budget.month) + text("interval '1 month'"),
                Date,
            ))
            & (Expense.deleted_at.is_(None)),
        )
        .group_by(Budget.id, Category.name)
        .order_by(Budget.month.desc())
    )
    if month:
        try:
            year, mo = map(int, month.split("-"))
        except ValueError:
            raise HTTPException(status_code=400, detail="month must be YYYY-MM")
        stmt = stmt.where(Budget.month == date(year, mo, 1))

    result = await db.execute(stmt)
    rows = result.all()

    return [
        BudgetOut(
            id=row.id,
            category_id=row.category_id,
            category_name=row.category_name,
            month=row.month,
            limit_amount=row.limit_amount,
            currency=row.currency,
            spent=row.spent,
            remaining=row.limit_amount - row.spent,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.post("", response_model=BudgetOut, status_code=201)
async def create_budget(body: BudgetCreate, db: AsyncSession = Depends(get_db)):
    # Normalize month to first day
    first_of_month = date(body.month.year, body.month.month, 1)

    # Check category exists
    cat = await db.get(Category, body.category_id)
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")

    # Check for duplicate budget (same category + month)
    existing = await db.execute(
        select(Budget).where(
            Budget.category_id == body.category_id,
            Budget.month == first_of_month,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Budget already exists for this category/month")

    budget = Budget(
        category_id=body.category_id,
        month=first_of_month,
        limit_amount=body.limit_amount,
        currency=body.currency,
    )
    db.add(budget)
    await db.commit()
    await db.refresh(budget)

    return BudgetOut(
        id=budget.id,
        category_id=budget.category_id,
        category_name=cat.name,
        month=budget.month,
        limit_amount=budget.limit_amount,
        currency=budget.currency,
        spent=0,
        remaining=budget.limit_amount,
        created_at=budget.created_at,
    )


@router.delete("/{budget_id}", status_code=204)
async def delete_budget(budget_id: int, db: AsyncSession = Depends(get_db)):
    budget = await db.get(Budget, budget_id)
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")
    await db.delete(budget)
    await db.commit()
