from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import ExchangeRate
from app.schemas import ExchangeRateOut, ExchangeRateSet, FxQuote
from app.services.fx import BASE_CURRENCY, get_rate, to_base

router = APIRouter(prefix="/exchange-rates", tags=["exchange-rates"])


@router.get("", response_model=list[ExchangeRateOut])
async def list_rates(db: AsyncSession = Depends(get_db)):
    """Latest cached rate per currency."""
    result = await db.execute(
        select(ExchangeRate)
        .distinct(ExchangeRate.target_currency)
        .order_by(ExchangeRate.target_currency, ExchangeRate.rate_date.desc())
    )
    return result.scalars().all()


@router.get("/quote", response_model=FxQuote)
async def quote(
    currency: str = Query(..., min_length=3, max_length=3),
    on_date: date | None = Query(default=None, alias="date", description="Defaults to today"),
    amount: Decimal | None = Query(default=None, gt=0),
    db: AsyncSession = Depends(get_db),
):
    """Rate for a currency on a date (fetched and cached if needed), optionally converting an amount."""
    on_date = on_date or date.today()
    rate = await get_rate(db, currency, on_date)
    await db.commit()
    return FxQuote(
        currency=currency.upper(),
        date=on_date,
        rate=rate,
        amount=amount,
        base_amount=to_base(amount, rate) if amount is not None and rate is not None else None,
    )


@router.post("", response_model=ExchangeRateOut)
async def set_rate(body: ExchangeRateSet, db: AsyncSession = Depends(get_db)):
    """Manually set a rate for a date (default today), overriding the fetched one.
    rate = 1 target_currency = X SGD."""
    target = body.target_currency.upper()
    if target == BASE_CURRENCY:
        raise HTTPException(status_code=400, detail="SGD is the base currency — rate is always 1.0")
    rate_date = body.rate_date or date.today()

    existing = await db.execute(
        select(ExchangeRate).where(
            ExchangeRate.target_currency == target,
            ExchangeRate.rate_date == rate_date,
        )
    )
    rate_obj = existing.scalar_one_or_none()

    if rate_obj:
        rate_obj.rate = body.rate
        rate_obj.source = "manual"
    else:
        rate_obj = ExchangeRate(target_currency=target, rate_date=rate_date, rate=body.rate, source="manual")
        db.add(rate_obj)

    await db.commit()
    await db.refresh(rate_obj)
    return rate_obj


@router.delete("/{target_currency}", status_code=204)
async def delete_rate(
    target_currency: str,
    on_date: date | None = Query(default=None, alias="date", description="Omit to delete all rates for the currency"),
    db: AsyncSession = Depends(get_db),
):
    stmt = delete(ExchangeRate).where(ExchangeRate.target_currency == target_currency.upper())
    if on_date:
        stmt = stmt.where(ExchangeRate.rate_date == on_date)
    result = await db.execute(stmt)
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Rate not found")
    await db.commit()
