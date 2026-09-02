import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import Category
from app.schemas import OcrResult
from app.services.vision import parse_receipt

router = APIRouter(prefix="/expenses", tags=["ocr"])

_ALLOWED_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
_MAX_SIZE = 20 * 1024 * 1024  # 20 MB
_MAX_BATCH = 10  # Gemini free tier is 15 RPM; keep one request well under that


async def _ocr_one(file: UploadFile, db: AsyncSession) -> OcrResult:
    if file.content_type not in _ALLOWED_TYPES:
        return OcrResult(
            filename=file.filename,
            error=f"Unsupported file type: {file.content_type}. Use JPEG or PNG.",
        )

    image_bytes = await file.read()
    if len(image_bytes) > _MAX_SIZE:
        return OcrResult(filename=file.filename, error="File too large (max 20 MB)")

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
        parsed = await parse_receipt(image_bytes)

        category_id = None
        category_name = parsed.get("category")
        if category_name:
            cat = await db.scalar(select(Category).where(Category.name == category_name))
            if cat:
                category_id = cat.id
            else:
                # fallback to "Others"
                cat = await db.scalar(select(Category).where(Category.name == "Others"))
                if cat:
                    category_id = cat.id
                    category_name = "Others"

        return OcrResult(
            filename=file.filename,
            date=parsed["date"],
            amount=parsed["amount"],
            currency=parsed["currency"],
            vendor=parsed["vendor"],
            category_id=category_id,
            category_name=category_name,
            raw_text=parsed["raw_text"],
            receipt_image_path=str(image_path),
        )
    except Exception as e:
        # clean up saved file on any failure past this point (vision call or DB lookup)
        image_path.unlink(missing_ok=True)
        return OcrResult(filename=file.filename, error=f"OCR failed: {e}")


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
    return [await _ocr_one(file, db) for file in files]
