from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Category, Expense
from app.schemas import CategoryCreate, CategoryOut

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[CategoryOut])
async def list_categories(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Category).order_by(Category.is_default.desc(), Category.name))
    return result.scalars().all()


@router.post("", response_model=CategoryOut, status_code=201)
async def create_category(body: CategoryCreate, db: AsyncSession = Depends(get_db)):
    exists = await db.scalar(select(Category).where(Category.name == body.name))
    if exists:
        raise HTTPException(status_code=409, detail="Category already exists")
    category = Category(name=body.name, is_default=False)
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return category


@router.delete("/{category_id}", status_code=204)
async def delete_category(category_id: int, db: AsyncSession = Depends(get_db)):
    category = await db.get(Category, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    if category.is_default:
        raise HTTPException(status_code=400, detail="Cannot delete a default category")
    # reassign any expenses that use this category
    expenses = await db.execute(
        select(Expense).where(Expense.category_id == category_id)
    )
    for expense in expenses.scalars().all():
        expense.category_id = None
    await db.delete(category)
    await db.commit()
