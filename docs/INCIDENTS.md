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
