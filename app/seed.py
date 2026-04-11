"""Seed default categories. Run once after alembic upgrade head."""
import asyncio

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Category

DEFAULT_CATEGORIES = [
    "Food",
    "Transport",
    "Utilities",
    "Rent",
    "Healthcare",
    "Shopping",
    "Entertainment",
    "Others",
]


async def seed_categories() -> None:
    async with SessionLocal() as session:
        for name in DEFAULT_CATEGORIES:
            exists = await session.scalar(select(Category).where(Category.name == name))
            if not exists:
                session.add(Category(name=name, is_default=True))
        await session.commit()
    print(f"Seeded {len(DEFAULT_CATEGORIES)} default categories.")


if __name__ == "__main__":
    asyncio.run(seed_categories())
