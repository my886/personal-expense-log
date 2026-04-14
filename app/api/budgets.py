from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
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
    stmt = select(Budget).order_by(Budget.month.desc())
    if month:
        try:
            year, mo = map(int, month.split("-"))
        except ValueError:
            raise HTTPException(status_code=400, detail="month must be YYYY-MM")
        stmt = stmt.where(Budget.month == date(year, mo, 1))

    result = await db.execute(stmt)
    budgets = result.scalars().all()

    out = []
    for b in budgets:
        # Calculate spent amount for this budget's month/category
        year, mo = b.month.year, b.month.month
        start = date(year, mo, 1)
        end = date(year + 1, 1, 1) if mo == 12 else date(year, mo + 1, 1)

        spent_result = await db.execute(
            select(func.coalesce(func.sum(
                func.coalesce(Expense.base_amount, Expense.amount)
            ), 0)).where(
                Expense.category_id == b.category_id,
                Expense.date >= start,
                Expense.date < end,
                Expense.deleted_at.is_(None),
            )
        )
        spent = spent_result.scalar()

        # Get category name
        cat_result = await db.execute(select(Category).where(Category.id == b.category_id))
        cat = cat_result.scalar_one_or_none()

        out.append(BudgetOut(
            id=b.id,
            category_id=b.category_id,
            category_name=cat.name if cat else None,
            month=b.month,
            limit_amount=b.limit_amount,
            currency=b.currency,
            spent=spent,
            remaining=b.limit_amount - spent,
            created_at=b.created_at,
        ))
    return out


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
