from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Category, Expense
from app.schemas import CategoryBreakdown, MonthlySummary

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/summary", response_model=MonthlySummary)
async def monthly_summary(
    month: str = Query(..., description="YYYY-MM"),
    currency: str = Query(default="MYR"),
    db: AsyncSession = Depends(get_db),
):
    try:
        year, mo = map(int, month.split("-"))
    except ValueError:
        raise HTTPException(status_code=400, detail="month must be YYYY-MM")

    start = date(year, mo, 1)
    end = date(year + 1, 1, 1) if mo == 12 else date(year, mo + 1, 1)

    base = select(Expense).where(
        Expense.date >= start,
        Expense.date < end,
        Expense.currency == currency,
    )

    # total
    total_result = await db.execute(
        select(func.coalesce(func.sum(Expense.amount), 0), func.count(Expense.id)).where(
            Expense.date >= start,
            Expense.date < end,
            Expense.currency == currency,
        )
    )
    total_amount, total_count = total_result.one()

    # by category
    breakdown_result = await db.execute(
        select(
            Expense.category_id,
            Category.name,
            func.sum(Expense.amount).label("total"),
            func.count(Expense.id).label("count"),
        )
        .outerjoin(Category, Expense.category_id == Category.id)
        .where(Expense.date >= start, Expense.date < end, Expense.currency == currency)
        .group_by(Expense.category_id, Category.name)
        .order_by(func.sum(Expense.amount).desc())
    )

    by_category = [
        CategoryBreakdown(
            category_id=row.category_id,
            category_name=row.name,
            total=row.total,
            count=row.count,
        )
        for row in breakdown_result.all()
    ]

    return MonthlySummary(
        month=month,
        total=Decimal(str(total_amount)),
        currency=currency,
        count=total_count,
        by_category=by_category,
    )
