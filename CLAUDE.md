# bank-platform

Multi-agent banking assistant, built against a reference architecture diagram
(`assets\ad3ccd54-9532-4b2b-b8f9-b837caf40af1_image.png`, "Step 14: Edge Layer
Security"). Coordinator + Accounts/Transaction/Service agents, backed by
Postgres, with MCP servers, LLM routing, and everything else in the diagram
deferred to later phases.

**Always check [PROGRESS.md](PROGRESS.md) first** — it's the authoritative
phase ledger (what's done, what's in progress, the agreed plan for current
work) and is kept up to date every session. **Check [PROBLEMS.md](PROBLEMS.md)**
for real issues already hit and how they were solved, before re-diagnosing
something that's been through this before.

## Stack

Python (>=3.13), FastAPI, SQLAlchemy 2.0, Postgres 17 via Docker, `psycopg`
(v3, not psycopg2), `uv` for dependency management, `pytest`. No agent
framework (LangGraph/CrewAI/etc.) — plain Python classes, by deliberate
choice (see PROGRESS.md's tech-stack discussion): not worth the indirection
until an LLM-driven reasoning loop actually needs it.

## Architecture (current, not the full diagram)

```
main.py (/chat endpoint)
  → coordinator.py — rule-based routing on "<agent>.<operation>" intent prefix
    → agents.py — AccountsAgent / TransactionAgent / ServiceAgent
      → crud_accounts.py / crud_transactions.py / crud_service.py
        → database.py / models.py → Postgres
```

- **No MCP layer yet.** Agents call `crud_*` functions directly. `interfaces.py`
  has stub `MCPClient`/`SessionStore` interfaces for the future retrofit, but
  they're unused. When MCP is introduced, each MCP server is a domain-owning
  microservice (not middleware) — see PROGRESS.md's MCP discussion.
- **No LLM yet.** Coordinator routing is a plain string-split + enum lookup,
  not an LLM call. This is intentional for now, not a placeholder bug.
- **Agents own business logic; `crud_*` stays "dumb" persistence.** Rules like
  overdraft checks live in the agent layer (or in one atomic `crud_*` function
  when the write must be atomic — see `create_transaction_and_update_balance`),
  never split across multiple agent-orchestrated calls, because that pattern
  won't survive the future MCP tool-call boundary.
- **Money uses `Decimal`, not `float`,** for all balance/amount arithmetic
  internally. `float()` conversion only happens at the JSON response boundary.
- **Error taxonomy:** `AgentResponse.error` is one of `invalid_intent`,
  `unknown_agent`, `unknown_operation`, `not_found`, `missing_field`,
  `insufficient_funds`, `invalid_status_transition`, `validation_error`.
  Domain exceptions live in `exceptions.py` and get caught per-agent, mapped
  to these codes — never let one propagate to FastAPI's default 500 handler.

## Running it

```bash
docker compose up -d          # Postgres 17, bank/bank@localhost:5432/bank_platform
uv run python -c "from models import Base; from database import engine; Base.metadata.create_all(engine)"  # tables (no migration tool yet)
uv run fastapi dev main.py    # dev server
uv run pytest -v              # requires the DB container running, no mocking
```

Port 5432 is also used by an unrelated project (`fastapi-postgresql-learning`)
on this machine — check `docker ps -a` before assuming which container is up.

## Conventions

- Branch: `main` (not `master`).
- Commits: create new commits, don't amend; end messages with the
  `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` trailer.
- `crud_*` files are split one per domain (not one shared `crud.py`), matching
  the agent split.
- Tests live in `tests/`, need `pythonpath = ["."]` in `pyproject.toml` to
  import root-level modules (no `src/` layout despite the empty `src/` dir —
  that's a leftover, not in use).
- When a real bug is found and fixed (not just a feature gap), add an entry
  to `PROBLEMS.md` using its template — problem, root cause, solution, why it
  mattered. When a phase/step completes or a design decision is made, update
  `PROGRESS.md`.
