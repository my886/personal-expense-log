# Expense Log System

Internal HTTP tool service called by hermes-agent (Nous Research agent framework) via Telegram.
No web frontend — hermes-agent handles conversation; this API provides data extraction + storage.

## Stack

- FastAPI + asyncpg + SQLAlchemy async
- PostgreSQL
- Vision LLM via OpenRouter for receipt parsing (`VISION_MODELS`, default Claude Haiku 5.5 → Qwen 3.8 Flash fallback)
- uv for packages

## Run

```bash
uv run uvicorn app.main:app --reload
```

## Env

Copy `.env.example` to `.env` and fill in values.

## Docs

- `docs/BACKLOG.md` — open features and architecture decision log
- `docs/INCIDENTS.md` — bug/incident log with root cause and fix (check here first when debugging)

## Known Quirks

- `receipt_image_path` is nullable — purging images sets it to NULL but expense records survive
- Vision model is chosen by benchmark on real receipts (see BACKLOG decisions); retry once on 429/5xx
- Categories: 8 seeded defaults (is_default=true); user-added have is_default=false
- `currency` defaults to SGD; non-SGD expenses auto-convert at the ECB rate for the expense date (`app/services/fx.py`), rate stored in `fx_rate`. ECB rates (Frankfurter) first, fawazahmed0 market rates for others (e.g. VND)
