"""
Exchange rates to SGD (base currency).

Rates are looked up by expense date: cached row in exchange_rates -> Frankfurter
(ECB reference rates, free, no key) -> fawazahmed0 currency-api (market rates, covers
currencies the ECB doesn't, e.g. VND) -> nearest cached rate as a last resort.

Both sources are queried as SGD -> X and inverted: the X -> SGD direction is rounded to
5 decimal places, which leaves only 2 significant figures for IDR/VND.
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
_FRANKFURTER_URL = "https://api.frankfurter.dev/v1/{date}"
_MARKET_URLS = (  # same data, two mirrors
    "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@{date}/v1/currencies/sgd.json",
    "https://{date}.currency-api.pages.dev/v1/currencies/sgd.json",
)
_TIMEOUT = 5.0
_RATE_PLACES = Decimal("0.0000000001")


def _invert(sgd_to_x) -> Decimal:
    return (Decimal(1) / Decimal(str(sgd_to_x))).quantize(_RATE_PLACES, rounding=ROUND_HALF_UP)


async def _fetch_ecb(client: httpx.AsyncClient, currency: str, on_date: date) -> tuple[Decimal, date] | None:
    """ECB has no weekend/holiday rates: the API returns the previous business day's
    rate along with that day's date. 404 = currency not covered by the ECB."""
    resp = await client.get(
        _FRANKFURTER_URL.format(date=on_date.isoformat()),
        params={"base": BASE_CURRENCY, "symbols": currency},
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    data = resp.json()
    if currency not in data.get("rates", {}):
        return None
    return _invert(data["rates"][currency]), date.fromisoformat(data["date"])


async def _fetch_market(client: httpx.AsyncClient, currency: str, on_date: date) -> tuple[Decimal, date] | None:
    for url in _MARKET_URLS:
        try:
            resp = await client.get(url.format(date=on_date.isoformat()))
            if resp.status_code == 404:
                continue
            resp.raise_for_status()
            data = resp.json()
            value = data[BASE_CURRENCY.lower()].get(currency.lower())
            return (_invert(value), date.fromisoformat(data["date"])) if value else None
        except Exception as e:
            logger.warning("FX: market source %s failed: %s", url.split("/")[2], e)
    return None


async def _fetch_rate(currency: str, on_date: date) -> tuple[Decimal, date, str] | None:
    """Fetch 1 currency = X SGD for on_date as (rate, published_date, source)."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        try:
            ecb = await _fetch_ecb(client, currency, on_date)
            if ecb:
                return *ecb, "ecb"
        except Exception as e:
            logger.warning("FX: ECB fetch failed for %s on %s: %s", currency, on_date, e)
        market = await _fetch_market(client, currency, on_date)
        if market:
            return *market, "market"
    logger.warning("FX: no rate for %s on %s from any source", currency, on_date)
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
        rate, published, source = fetched
        # Today's rate may not be published yet — don't pin yesterday's rate to today.
        if on_date < date.today() or published == on_date:
            await db.execute(
                insert(ExchangeRate)
                .values(target_currency=currency, rate_date=on_date, rate=rate, source=source)
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
    return (Decimal(base_amount) / Decimal(amount)).quantize(_RATE_PLACES, rounding=ROUND_HALF_UP)


async def apply_fx(db: AsyncSession, expense) -> None:
    """Set expense.base_amount / expense.fx_rate from amount, currency and date.
    Leaves both NULL if no rate is available."""
    rate = await get_rate(db, expense.currency, expense.date)
    expense.fx_rate = rate
    expense.base_amount = to_base(expense.amount, rate) if rate is not None else None
