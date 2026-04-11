# Backlog

## Open

- [ ] Redis + RQ async OCR queue (Phase 2)
- [ ] MCP server wrapper for hermes-agent tool discovery (Phase 2)
- [ ] LLM insights / forecasting (Phase 2)
- [ ] Auth / single-user login (Phase 2, if exposed publicly)
- [ ] PDF support (Phase 2, single-page only via pdf2image)
- [ ] Tags on expenses (Phase 2)
- [ ] Scheduled image purge job (Phase 3)

## Decisions Log

### 2026-04-11 — Initial Architecture

| Decision | Choice | Rationale |
|---|---|---|
| Interface | Telegram via hermes-agent only | System is a tool, not a user-facing app |
| OCR engine | Gemini Vision (no Tesseract) | Vision LLM is more accurate on real receipts; free tier sufficient |
| LLM | Gemini 1.5/2.0 Flash | Free tier (1500 RPD), vision capability |
| LLM abstraction | Single vision.py service | Swap to GLM-4V/OpenAI/Claude with one file change |
| Queue | Deferred to Phase 2 | Sync OCR fine for 1 user at <3s |
| Auth | Deferred | Internal localhost service |
| Image storage | Local FS, nullable path | Purge deletes files + sets path NULL; records survive |
| Currency | Default MYR, per-expense override | Single user in Malaysia |
