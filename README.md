# Expense Log

Lightweight expense tracking API. Called by hermes-agent as an internal tool via Telegram.

## Setup

```bash
cp .env.example .env
# fill in DATABASE_URL and GEMINI_API_KEY

uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 8100
```

## API Docs

`http://127.0.0.1:8100/docs`

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | /expenses/ocr | Upload receipt image → parsed fields |
| POST | /expenses | Save confirmed expense |
| GET | /expenses | List expenses |
| GET/PUT/DELETE | /expenses/{id} | Single expense |
| GET/POST | /categories | List / add category |
| DELETE | /categories/{id} | Remove custom category |
| GET | /analytics/summary | Monthly totals + breakdown |
| DELETE | /storage/images | Purge old images |
