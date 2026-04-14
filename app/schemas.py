from __future__ import annotations

import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, Field


# ── Category ───────────────────────────────────────────���──────────────────────

class CategoryOut(BaseModel):
    id: int
    name: str
    is_default: bool

    model_config = {"from_attributes": True}


class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


# ── Expense ────────────────────���──────────────────────────────────────────────

class ExpenseCreate(BaseModel):
    amount: Decimal = Field(..., gt=0, decimal_places=2)
    currency: str = Field(default="SGD", min_length=3, max_length=3)
    date: dt.date
    category_id: int | None = None
    vendor: str | None = Field(default=None, max_length=255)
    notes: str | None = None
    raw_text: str | None = None
    receipt_image_path: str | None = None
    source: str = Field(default="manual", pattern="^(manual|ocr)$")


class ExpenseUpdate(BaseModel):
    amount: Decimal | None = Field(default=None, gt=0, decimal_places=2)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    date: dt.date | None = None
    category_id: int | None = None
    vendor: str | None = Field(default=None, max_length=255)
    notes: str | None = None


class ExpenseOut(BaseModel):
    id: int
    amount: Decimal
    currency: str
    date: dt.date
    category_id: int | None
    category_name: str | None
    vendor: str | None
    notes: str | None
    raw_text: str | None
    receipt_image_path: str | None
    source: str
    created_at: dt.datetime

    model_config = {"from_attributes": True}


# ── OCR result (not saved) ───���────────────────────────────────────────────────

class OcrResult(BaseModel):
    date: dt.date | None = None
    amount: Decimal | None = None
    currency: str = "SGD"
    vendor: str | None = None
    category_id: int | None = None
    category_name: str | None = None
    raw_text: str | None = None


# ── Analytics ───────────────────���────────────────────────────────���────────────

class CategoryBreakdown(BaseModel):
    category_id: int | None
    category_name: str | None
    total: Decimal
    count: int


class MonthlySummary(BaseModel):
    month: str          # "YYYY-MM"
    total: Decimal
    currency: str
    count: int
    by_category: list[CategoryBreakdown]


# ── Storage purge ─────────────────────────────���───────────────────────────────

class PurgeResult(BaseModel):
    purged_count: int
