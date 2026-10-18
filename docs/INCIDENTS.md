# Incidents & Bug Log

Running log of bugs found, root cause, and fix. Purpose: track problems to improve technical knowledge over time.

---

## 2026-05-23 — Stale DB connection causes 500 on POST /expenses

**Symptom:** Expense logging intermittently fails with 500 after service has been idle (e.g. overnight). OCR step succeeds but saving the confirmed expense fails.

**Error:**
```
asyncpg.exceptions.InterfaceError: connection is closed
sqlalchemy.exc.InterfaceError: connection is closed
```

**Root cause:** PostgreSQL drops idle connections server-side after a timeout. SQLAlchemy's async connection pool holds references to these dead connections and reuses them without checking liveness first.

**Fix:** Added `pool_pre_ping=True` to `create_async_engine` in `app/database.py`. SQLAlchemy now issues a lightweight `SELECT 1` before handing out a pooled connection, automatically replacing it if dropped.

**Lesson:** Always enable `pool_pre_ping=True` on long-running async services backed by PostgreSQL. Without it, any idle period longer than the server's `tcp_keepalives_idle` or `idle_in_transaction_session_timeout` will produce stale-connection 500s on the next request.

---

## 2026-10-18 — Stale flat FX rate; non-MYR foreign expenses missing from SGD totals

**Symptom:** All MYR expenses converted at a hand-set 0.33 SGD/MYR (set 2026-04-15, never updated; actual 0.312–0.322) — overstated by 3–6%. A USD 17.40 expense had `base_amount` NULL, so analytics' `coalesce(base_amount, amount)` counted it as S$17.40 instead of S$22.12. 23 pre-migration SGD rows also had NULL `base_amount`. hermes-agent separately converted JB statements at its own ~3.18 MYR/SGD.

**Root cause:** `exchange_rates` held one manual rate per currency with no date and no fetch; currencies without a row silently got no conversion.

**Fix:** `exchange_rates` now keyed by (currency, rate_date). `app/services/fx.py` looks up the rate for the *expense date*: cache → Frankfurter (ECB, free, no key) → nearest cached rate. Each expense stores `fx_rate` (rate used, or implied rate when the actual SGD debit is supplied as `base_amount`). Date changes re-convert. `GET /exchange-rates/quote` for ad-hoc lookups. `scripts/backfill_fx.py` recomputed history (total −S$73.29). hermes skill updated to send MYR and let the server convert.

**Lesson:** Store the rate used alongside every converted amount, and source rates by transaction date — a single "current" rate silently drifts.
