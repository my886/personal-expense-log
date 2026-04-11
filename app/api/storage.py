import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Expense
from app.schemas import PurgeResult

router = APIRouter(prefix="/storage", tags=["storage"])


@router.delete("/images", response_model=PurgeResult)
async def purge_images(
    older_than_days: int = Query(default=90, ge=0, description="Delete images older than N days"),
    db: AsyncSession = Depends(get_db),
):
    """
    Delete receipt image files older than N days.
    Sets receipt_image_path to NULL on affected expense rows — records remain intact.
    """
    cutoff = datetime.now(tz=timezone.utc).timestamp() - older_than_days * 86400

    result = await db.execute(
        select(Expense).where(Expense.receipt_image_path.is_not(None))
    )
    expenses = result.scalars().all()

    purged = 0
    for expense in expenses:
        path = Path(expense.receipt_image_path)
        if not path.exists():
            # file already gone — just clear the reference
            expense.receipt_image_path = None
            purged += 1
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            expense.receipt_image_path = None
            purged += 1
            continue
        if mtime < cutoff:
            path.unlink(missing_ok=True)
            expense.receipt_image_path = None
            purged += 1

    await db.commit()
    return PurgeResult(purged_count=purged)
