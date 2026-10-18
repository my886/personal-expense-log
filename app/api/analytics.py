from datetime import date, timedelta
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
    db: AsyncSession = Depends(get_db),
):
    try:
        year, mo = map(int, month.split("-"))
    except ValueError:
        raise HTTPException(status_code=400, detail="month must be YYYY-MM")

    start = date(year, mo, 1)
    end = date(year + 1, 1, 1) if mo == 12 else date(year, mo + 1, 1)

    # Use base_amount (SGD equivalent), fall back to amount for SGD entries
    amount_expr = func.coalesce(Expense.base_amount, Expense.amount)

    # Total in SGD, split into fixed (linked to a recurring template) and variable
    total_result = await db.execute(
        select(
            func.coalesce(func.sum(amount_expr), 0),
            func.count(Expense.id),
            func.coalesce(func.sum(amount_expr).filter(Expense.recurring_id.is_not(None)), 0),
        ).where(
            Expense.date >= start,
            Expense.date < end,
            Expense.deleted_at.is_(None),
        )
    )
    total_amount, total_count, fixed_amount = total_result.one()
    variable_amount = Decimal(str(total_amount)) - Decimal(str(fixed_amount))

    # By category in SGD
    breakdown_result = await db.execute(
        select(
            Expense.category_id,
            Category.name,
            func.coalesce(func.sum(amount_expr), 0).label("total"),
            func.count(Expense.id).label("count"),
        )
        .outerjoin(Category, Expense.category_id == Category.id)
        .where(
            Expense.date >= start,
            Expense.date < end,
            Expense.deleted_at.is_(None),
        )
        .group_by(Expense.category_id, Category.name)
        .order_by(func.sum(amount_expr).desc())
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

    # Calculate daily average
    days_in_month = (end - start).days
    today = date.today()
    if today.year == year and today.month == mo:
        # Partial month — average over days elapsed so far
        days = max((today - start).days, 1)
    else:
        days = days_in_month
    daily_avg = Decimal(str(total_amount)) / days
    variable_daily_avg = variable_amount / days

    return MonthlySummary(
        month=month,
        total=Decimal(str(total_amount)),
        base_total=Decimal(str(total_amount)),
        currency="SGD",
        count=total_count,
        daily_avg=round(daily_avg, 2),
        fixed_total=Decimal(str(fixed_amount)),
        variable_total=variable_amount,
        variable_daily_avg=round(variable_daily_avg, 2),
        by_category=by_category,
    )
