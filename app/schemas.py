from __future__ import annotations

import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


# ── Category ──────────────────────────────────────────────────────────────────

class CategoryOut(BaseModel):
    id: int
    name: str
    is_default: bool

    model_config = {"from_attributes": True}


class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


# ── Expense ───────────────────────────────────────────────────────────────────

VALID_PAYMENT_METHODS = {"cash", "card", "grabpay", "paynow", "nets", "online", "other"}


class ExpenseCreate(BaseModel):
    amount: Decimal = Field(..., gt=0, decimal_places=2)
    currency: str = Field(default="SGD", min_length=3, max_length=3)
    base_amount: Decimal | None = Field(default=None, decimal_places=2)
    date: dt.date
    category_id: int | None = None
    vendor: str | None = Field(default=None, max_length=255)
    payment_method: str | None = Field(default=None, max_length=20)
    location: str | None = Field(default=None, max_length=255)
    tags: list[str] | None = None
    notes: str | None = None
    raw_text: str | None = None
    receipt_image_path: str | None = None
    source: str = Field(default="manual", pattern="^(manual|ocr)$")

    @field_validator("payment_method")
    @classmethod
    def validate_payment_method(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_PAYMENT_METHODS:
            raise ValueError(f"payment_method must be one of {sorted(VALID_PAYMENT_METHODS)}")
        return v


class ExpenseUpdate(BaseModel):
    amount: Decimal | None = Field(default=None, gt=0, decimal_places=2)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    base_amount: Decimal | None = Field(default=None, decimal_places=2)
    date: dt.date | None = None
    category_id: int | None = None
    vendor: str | None = Field(default=None, max_length=255)
    payment_method: str | None = Field(default=None, max_length=20)
    location: str | None = Field(default=None, max_length=255)
    tags: list[str] | None = None
    notes: str | None = None

    @field_validator("payment_method")
    @classmethod
    def validate_payment_method(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_PAYMENT_METHODS:
            raise ValueError(f"payment_method must be one of {sorted(VALID_PAYMENT_METHODS)}")
        return v


class ExpenseOut(BaseModel):
    id: int
    amount: Decimal
    currency: str
    base_amount: Decimal | None = None
    fx_rate: Decimal | None = None
    date: dt.date
    category_id: int | None
    category_name: str | None
    vendor: str | None
    payment_method: str | None = None
    location: str | None = None
    tags: list[str] | None = None
    notes: str | None
    raw_text: str | None
    receipt_image_path: str | None
    source: str
    created_at: dt.datetime

    model_config = {"from_attributes": True}


# ── OCR result (not saved) ────────────────────────────────────────────────────

class OcrResult(BaseModel):
    filename: str | None = None
    date: dt.date | None = None
    amount: Decimal | None = None
    currency: str = "SGD"
    currency_confirmed: bool = False    # True only if the receipt itself shows the currency
    currency_note: str | None = None    # evidence used, or why the currency was assumed
    vendor: str | None = None
    category_id: int | None = None
    category_name: str | None = None
    raw_text: str | None = None
    receipt_image_path: str | None = None
    error: str | None = None


# ── Analytics ─────────────────────────────────────────────────────────────────

class CategoryBreakdown(BaseModel):
    category_id: int | None
    category_name: str | None
    total: Decimal
    count: int


class MonthlySummary(BaseModel):
    month: str          # "YYYY-MM"
    total: Decimal
    base_total: Decimal | None = None
    currency: str
    count: int
    daily_avg: Decimal | None = None
    by_category: list[CategoryBreakdown]


# ── Budget ────────────────────────────────────────────────────────────────────

class BudgetCreate(BaseModel):
    category_id: int
    month: dt.date      # first day of month, e.g. 2026-04-01
    limit_amount: Decimal = Field(..., gt=0, decimal_places=2)
    currency: str = Field(default="SGD", min_length=3, max_length=3)


class BudgetOut(BaseModel):
    id: int
    category_id: int
    category_name: str | None = None
    month: dt.date
    limit_amount: Decimal
    currency: str
    spent: Decimal | None = None
    remaining: Decimal | None = None
    created_at: dt.datetime

    model_config = {"from_attributes": True}


# ── Storage purge ─────────────────────────────────────────────────────────────

class PurgeResult(BaseModel):
    purged_count: int


# ── Exchange Rate ─────────────────────────────────────────────────────────────

class ExchangeRateSet(BaseModel):
    """Set or update an exchange rate. rate = how many SGD per 1 unit of target currency."""
    target_currency: str = Field(..., min_length=3, max_length=3)
    rate: Decimal = Field(..., gt=0, decimal_places=6)
    rate_date: dt.date | None = None  # defaults to today


class ExchangeRateOut(BaseModel):
    id: int
    target_currency: str
    rate_date: dt.date
    rate: Decimal
    source: str
    updated_at: dt.datetime

    model_config = {"from_attributes": True}


class FxQuote(BaseModel):
    currency: str
    date: dt.date
    rate: Decimal | None    # 1 currency = X SGD; None if unavailable
    amount: Decimal | None = None
    base_amount: Decimal | None = None
