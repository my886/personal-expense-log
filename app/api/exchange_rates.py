from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import ExchangeRate
from app.schemas import ExchangeRateSet, ExchangeRateOut

router = APIRouter(prefix="/exchange-rates", tags=["exchange-rates"])


@router.get("", response_model=list[ExchangeRateOut])
async def list_rates(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ExchangeRate).order_by(ExchangeRate.target_currency))
    return result.scalars().all()


@router.post("", response_model=ExchangeRateOut)
async def set_rate(body: ExchangeRateSet, db: AsyncSession = Depends(get_db)):
    """Create or update an exchange rate. rate = 1 target_currency = X SGD."""
    target = body.target_currency.upper()
    if target == "SGD":
        raise HTTPException(status_code=400, detail="SGD is the base currency — rate is always 1.0")

    existing = await db.execute(
        select(ExchangeRate).where(ExchangeRate.target_currency == target)
    )
    rate_obj = existing.scalar_one_or_none()

    if rate_obj:
        rate_obj.rate = body.rate
    else:
        rate_obj = ExchangeRate(target_currency=target, rate=body.rate)
        db.add(rate_obj)

    await db.commit()
    await db.refresh(rate_obj)
    return rate_obj


@router.delete("/{target_currency}", status_code=204)
async def delete_rate(target_currency: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ExchangeRate).where(ExchangeRate.target_currency == target_currency.upper())
    )
    rate_obj = result.scalar_one_or_none()
    if not rate_obj:
        raise HTTPException(status_code=404, detail="Rate not found")
    await db.delete(rate_obj)
    await db.commit()
