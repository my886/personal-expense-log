from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import budgets, categories, expenses, exchange_rates, ocr, analytics, recurring, storage


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield  # startup / shutdown hooks go here when needed


app = FastAPI(
    title="Expense Log",
    description="Internal expense tracking API for hermes-agent.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(ocr.router)         # POST /expenses/ocr — must be before expenses router
app.include_router(expenses.router)    # CRUD /expenses
app.include_router(categories.router)  # /categories
app.include_router(budgets.router)     # /budgets
app.include_router(exchange_rates.router)  # /exchange-rates
app.include_router(analytics.router)   # /analytics/summary
app.include_router(recurring.router)   # /recurring templates, status, run
app.include_router(storage.router)     # DELETE /storage/images


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok"}
