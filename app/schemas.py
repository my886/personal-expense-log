from __future__ import annotations

import datetime as dt
import re
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
    recurring_id: int | None = None  # link to a recurring template (fixed cost); auto-matched if omitted

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
    recurring_id: int | None = None  # set null to unlink

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
    recurring_id: int | None = None
    is_fixed: bool = False
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
    fixed_total: Decimal = Decimal("0")       # expenses linked to recurring templates
    variable_total: Decimal = Decimal("0")
    variable_daily_avg: Decimal | None = None  # comparable across months, unlike daily_avg
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


# ── Recurring ─────────────────────────────────────────────────────────────────

class RecurringCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    amount: Decimal = Field(..., gt=0, decimal_places=2)
    currency: str = Field(default="SGD", min_length=3, max_length=3)
    category_id: int
    vendor: str | None = Field(default=None, max_length=255)
    payment_method: str | None = Field(default=None, max_length=20)
    notes: str | None = None
    match: str | None = Field(default=None, max_length=255, description="Regex on vendor/notes to auto-link logged expenses")
    day_of_month: int = Field(..., ge=1, le=31)
    auto_create: bool = False
    start_month: dt.date | None = None  # defaults to the current month
    end_month: dt.date | None = None

    @field_validator("payment_method")
    @classmethod
    def validate_payment_method(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_PAYMENT_METHODS:
            raise ValueError(f"payment_method must be one of {sorted(VALID_PAYMENT_METHODS)}")
        return v

    @field_validator("match")
    @classmethod
    def validate_match(cls, v: str | None) -> str | None:
        if v is not None:
            try:
                re.compile(v)
            except re.error as e:
                raise ValueError(f"match is not a valid regex: {e}")
        return v


class RecurringUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    amount: Decimal | None = Field(default=None, gt=0, decimal_places=2)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    category_id: int | None = None
    vendor: str | None = Field(default=None, max_length=255)
    payment_method: str | None = Field(default=None, max_length=20)
    notes: str | None = None
    match: str | None = Field(default=None, max_length=255)
    day_of_month: int | None = Field(default=None, ge=1, le=31)
    auto_create: bool | None = None
    active: bool | None = None
    start_month: dt.date | None = None
    end_month: dt.date | None = None

    @field_validator("payment_method")
    @classmethod
    def validate_payment_method(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_PAYMENT_METHODS:
            raise ValueError(f"payment_method must be one of {sorted(VALID_PAYMENT_METHODS)}")
        return v

    @field_validator("match")
    @classmethod
    def validate_match(cls, v: str | None) -> str | None:
        if v is not None:
            try:
                re.compile(v)
            except re.error as e:
                raise ValueError(f"match is not a valid regex: {e}")
        return v


class RecurringOut(BaseModel):
    id: int
    name: str
    amount: Decimal
    currency: str
    category_id: int
    category_name: str | None = None
    vendor: str | None
    payment_method: str | None
    notes: str | None
    match: str | None
    day_of_month: int
    auto_create: bool
    active: bool
    start_month: dt.date
    end_month: dt.date | None
    created_at: dt.datetime

    model_config = {"from_attributes": True}


class RecurringStatus(BaseModel):
    recurring_id: int
    name: str
    category_name: str | None
    due_date: dt.date
    auto_create: bool
    status: str                         # 'logged' | 'due' (past due date, not logged) | 'upcoming'
    expected_amount: Decimal            # template amount, in template currency
    currency: str
    expected_base_amount: Decimal | None  # SGD estimate
    expense_id: int | None = None
    base_amount: Decimal | None = None  # actual SGD amount if logged


# ── Storage purge ─────────────────────────────────────────────────────────────

class PurgeResult(BaseModel):
    purged_count: int


# ── Exchange Rate ─────────────────────────────────────────────────────────────

class ExchangeRateSet(BaseModel):
    """Set or update an exchange rate. rate = how many SGD per 1 unit of target currency."""
    target_currency: str = Field(..., min_length=3, max_length=3)
    rate: Decimal = Field(..., gt=0, decimal_places=10)
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
