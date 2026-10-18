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

### 2026-10-18 — Vision model: Gemini direct → OpenRouter (Claude Haiku 5.5)

Benchmarked on 23 real SG receipts (truth = logged expenses) + 10 synthetic CN/JP/VN/ID/EU receipts, same prompt.

| Model | Amount | Wrong dates | Avg latency | $/receipt |
|---|---|---|---|---|
| anthropic/claude-haiku-5.5 | 23/23 | 0 | 3.4s | 0.0005 |
| qwen/qwen3.8-flash | 23/23 | 2 (0 after prompt fix) | 14.2s | 0.0007 |
| google/gemini-3.8-flash | 23/23 | 1 | 11.8s | 0.0044 |
| openai/gpt-5.6-luna | 23/23 | 3 | 5.2s | 0.0009 |
| google/gemini-2.5-flash (previous) | 23/23 | 3 | 4.3s | 0.0013 |

| Decision | Choice | Rationale |
|---|---|---|
| Model | Haiku 5.5, Qwen 3.8 Flash fallback (`VISION_MODELS`) | No wrong dates (returns null instead of guessing), fastest, cheapest; Qwen accurate but slow |
| Provider | OpenRouter (paid) | Gemini free tier was 5 RPM with 503s (5/8 calls failed in a test); paid traffic not used for training; model swap = config change |
| Currency | Evidence-only, SGD/trip fallback | See INCIDENTS 2026-10-18; supports SGD/MYR/CNY/JPY/VND/IDR/EUR clues + any explicit ISO code |
