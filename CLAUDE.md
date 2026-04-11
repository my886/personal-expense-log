# Expense Log System

Internal HTTP tool service called by hermes-agent (Nous Research agent framework) via Telegram.
No web frontend — hermes-agent handles conversation; this API provides data extraction + storage.

## Stack

- FastAPI + asyncpg + SQLAlchemy async
- PostgreSQL
- Gemini Flash (vision LLM for receipt parsing)
- uv for packages

## Run

```bash
uv run uvicorn app.main:app --reload
```

## Env

Copy `.env.example` to `.env` and fill in values.

## Known Quirks

- `receipt_image_path` is nullable — purging images sets it to NULL but expense records survive
- Gemini free tier: 15 RPM / 1500 RPD — fine for personal use; retry once on 429
- Categories: 8 seeded defaults (is_default=true); user-added have is_default=false
- `currency` defaults to MYR; override per-expense for foreign receipts
