"""
Exchange rates to SGD (base currency).

Rates are looked up by expense date: cached row in exchange_rates -> Frankfurter
(ECB reference rates, free, no key) -> nearest cached rate as a last resort.
"""
import logging
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

import httpx
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ExchangeRate

logger = logging.getLogger(__name__)

BASE_CURRENCY = "SGD"
_API_URL = "https://api.frankfurter.dev/v1/{date}"
_TIMEOUT = 5.0


async def _fetch_rate(currency: str, on_date: date) -> tuple[Decimal, date] | None:
    """Fetch 1 currency = X SGD for on_date. ECB has no weekend/holiday rates, so the
    API returns the previous business day's rate along with that day's date."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                _API_URL.format(date=on_date.isoformat()),
                params={"base": currency, "symbols": BASE_CURRENCY},
            )
        if resp.status_code == 404:
            logger.warning("FX: no rate for %s on %s (unsupported currency?)", currency, on_date)
            return None
        resp.raise_for_status()
        data = resp.json()
        return Decimal(str(data["rates"][BASE_CURRENCY])), date.fromisoformat(data["date"])
    except Exception as e:
        logger.warning("FX: fetch failed for %s on %s: %s", currency, on_date, e)
        return None


async def get_rate(db: AsyncSession, currency: str, on_date: date) -> Decimal | None:
    """Return how many SGD 1 unit of `currency` was worth on `on_date`, or None."""
    currency = currency.upper()
    if currency == BASE_CURRENCY:
        return Decimal("1")
    on_date = min(on_date, date.today())  # no rates for future dates

    cached = await db.scalar(
        select(ExchangeRate.rate).where(
            ExchangeRate.target_currency == currency,
            ExchangeRate.rate_date == on_date,
        )
    )
    if cached is not None:
        return cached

    fetched = await _fetch_rate(currency, on_date)
    if fetched:
        rate, published = fetched
        # Today's rate may not be published yet — don't pin yesterday's rate to today.
        if on_date < date.today() or published == on_date:
            await db.execute(
                insert(ExchangeRate)
                .values(target_currency=currency, rate_date=on_date, rate=rate, source="ecb")
                .on_conflict_do_nothing(constraint="uq_exchange_rate_currency_date")
            )
        return rate

    nearest = await db.scalar(
        select(ExchangeRate.rate)
        .where(ExchangeRate.target_currency == currency)
        .order_by(func.abs(ExchangeRate.rate_date - on_date))
        .limit(1)
    )
    if nearest is not None:
        logger.warning("FX: using nearest cached %s rate for %s", currency, on_date)
    return nearest


def to_base(amount: Decimal, rate: Decimal) -> Decimal:
    return (Decimal(amount) * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def implied_rate(amount: Decimal, base_amount: Decimal) -> Decimal:
    """Rate implied by a user-supplied SGD amount (e.g. the actual card/bank debit)."""
    return (Decimal(base_amount) / Decimal(amount)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


async def apply_fx(db: AsyncSession, expense) -> None:
    """Set expense.base_amount / expense.fx_rate from amount, currency and date.
    Leaves both NULL if no rate is available."""
    rate = await get_rate(db, expense.currency, expense.date)
    expense.fx_rate = rate
    expense.base_amount = to_base(expense.amount, rate) if rate is not None else None
