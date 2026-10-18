import os
import uuid
from datetime import date, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import Category, Expense
from app.schemas import OcrResult, OcrSplit
from app.services.split import split_receipt
from app.services.vision import parse_receipts

router = APIRouter(prefix="/expenses", tags=["ocr"])

_ALLOWED_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
_MAX_SIZE = 20 * 1024 * 1024  # 20 MB
_MAX_BATCH = 10  # Gemini free tier is 15 RPM; keep one request well under that
_DEFAULT_CURRENCY = "SGD"   # user lives in Singapore
_TRIP_WINDOW_DAYS = 3       # recent foreign-currency expenses within this window suggest a trip
_TRIP_MIN_EXPENSES = 2


async def _resolve_currency(parsed: dict, db: AsyncSession) -> tuple[str, bool, str]:
    """Return (currency, confirmed, note). Trust the model only when it cites evidence on the
    receipt; otherwise infer from recent expenses (on a trip?) and fall back to SGD."""
    if parsed.get("currency") and parsed.get("currency_evidence"):
        return parsed["currency"], True, parsed["currency_evidence"]

    around = parsed.get("date") or date.today()
    trip = (
        await db.execute(
            select(Expense.currency, func.count())
            .where(
                Expense.currency != _DEFAULT_CURRENCY,
                Expense.deleted_at.is_(None),
                Expense.date.between(around - timedelta(days=_TRIP_WINDOW_DAYS), around + timedelta(days=_TRIP_WINDOW_DAYS)),
            )
            .group_by(Expense.currency)
            .order_by(func.count().desc())
            .limit(1)
        )
    ).first()
    if trip and trip[1] >= _TRIP_MIN_EXPENSES:
        return trip[0], False, f"no currency on receipt; {trip[1]} {trip[0]} expenses within {_TRIP_WINDOW_DAYS} days suggest a trip"
    return _DEFAULT_CURRENCY, False, "no currency on receipt; assumed SGD"


async def _resolve_category(name: str | None, db: AsyncSession) -> tuple[int | None, str | None]:
    """Category id/name for a model-picked name; unknown names fall back to "Others"."""
    if not name:
        return None, None
    cat = await db.scalar(select(Category).where(Category.name == name))
    if not cat:
        cat = await db.scalar(select(Category).where(Category.name == "Others"))
    return (cat.id, cat.name) if cat else (None, name)


async def _to_result(parsed: dict, filename: str | None, image_path: str, index: int, count: int,
                     db: AsyncSession) -> OcrResult:
    category_id, category_name = await _resolve_category(parsed.get("category"), db)
    currency, currency_confirmed, currency_note = await _resolve_currency(parsed, db)

    raw_splits, unexplained = split_receipt(parsed["amount"], parsed.get("category"), parsed["items"], parsed["adjustments"])
    splits = []
    for s in raw_splits:
        split_id, split_name = await _resolve_category(s["category"], db)
        splits.append(OcrSplit(category_id=split_id, category_name=split_name, amount=s["amount"], items=s["items"]))

    return OcrResult(
        filename=filename,
        receipt_index=index,
        receipt_count=count,
        date=parsed["date"],
        amount=parsed["amount"],
        currency=currency,
        currency_confirmed=currency_confirmed,
        currency_note=currency_note,
        vendor=parsed["vendor"],
        category_id=category_id,
        category_name=category_name,
        raw_text=parsed["raw_text"],
        receipt_image_path=image_path,
        splits=splits,
        unexplained=unexplained,
    )


async def _ocr_one(file: UploadFile, db: AsyncSession) -> list[OcrResult]:
    """One result per receipt found in the image; a single result with `error` if the file fails."""
    if file.content_type not in _ALLOWED_TYPES:
        return [OcrResult(
            filename=file.filename,
            error=f"Unsupported file type: {file.content_type}. Use JPEG or PNG.",
        )]

    image_bytes = await file.read()
    if len(image_bytes) > _MAX_SIZE:
        return [OcrResult(filename=file.filename, error="File too large (max 20 MB)")]

    # save image to uploads dir
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(exist_ok=True)
    ext = Path(file.filename or "receipt.jpg").suffix or ".jpg"
    filename = f"{uuid.uuid4().hex}{ext}"
    image_path = upload_dir / filename
    image_path.write_bytes(image_bytes)

    # everything past this point can fail independently per file (Gemini call,
    # DB lookup) — any failure here must not take down the rest of the batch
    try:
        receipts = await parse_receipts(image_bytes)
        return [
            await _to_result(parsed, file.filename, str(image_path), i, len(receipts), db)
            for i, parsed in enumerate(receipts, start=1)
        ]
    except Exception as e:
        # clean up saved file on any failure past this point (vision call or DB lookup)
        image_path.unlink(missing_ok=True)
        return [OcrResult(filename=file.filename, error=f"OCR failed: {e}")]


@router.post("/ocr", response_model=list[OcrResult])
async def ocr_receipt(
    files: list[UploadFile],
    db: AsyncSession = Depends(get_db),
):
    if len(files) > _MAX_BATCH:
        raise HTTPException(
            status_code=413,
            detail=f"Too many files: {len(files)} (max {_MAX_BATCH} per request)",
        )
    # sequential, not concurrent: Gemini free tier is 15 RPM
    # flat list: an image with several receipts yields several results (same receipt_image_path)
    return [result for file in files for result in await _ocr_one(file, db)]
