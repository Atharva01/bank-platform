# bank-platform

Multi-agent banking assistant, built against a reference architecture diagram
(`assets\ad3ccd54-9532-4b2b-b8f9-b837caf40af1_image.png`, "Step 14: Edge Layer
Security"). Coordinator + Accounts/Transaction/Service agents, each backed by
its own MCP server, backed by Postgres. LLM routing and everything else in
the diagram (Edge Layer, Auth, Session Store, PII Redaction, Observability,
Eval Suite) deferred to later phases.

**Always check [PROGRESS.md](PROGRESS.md) first** — it's the authoritative
phase ledger (what's done, what's in progress, the agreed plan for current
work) and is kept up to date every session. **Check [PROBLEMS.md](PROBLEMS.md)**
for real issues already hit and how they were solved, before re-diagnosing
something that's been through this before.

## Stack

Python (>=3.13), FastAPI, SQLAlchemy 2.0, Postgres 17 via Docker, `psycopg`
(v3, not psycopg2), `uv` for dependency management, `pytest`, `hatchling` as
the build backend (src layout, installed editable via `uv sync`). No agent
framework (LangGraph/CrewAI/etc.) — plain Python classes, by deliberate
choice: not worth the indirection until an LLM-driven reasoning loop actually
needs it. No real MCP protocol (`mcp`/FastMCP) either, by deliberate choice —
see the MCP section below.

## Layout

```
src/bank_platform/       — the package; all internal imports are
                            "from bank_platform.x import y" (absolute, never
                            relative or bare)
  main.py                — FastAPI app, single /chat endpoint
  coordinator.py          — rule-based routing on "<agent>.<operation>" intent
  agents.py               — AccountsAgent / TransactionAgent / ServiceAgent:
                             intent parsing + tool-call translation only, no
                             DB/session code
  interfaces.py           — MCPClient ABC + InProcessMCPClient (the real
                             implementation in use) + default_mcp_client
  accounts_server.py       — MCP server: owns Account + its validation
  transactions_server.py   — MCP server: owns Transaction + Account.balance
                              (the only server spanning two tables)
  service_server.py        — MCP server: owns ServiceRequest + its validation
                              and status state machine
  crud_accounts.py / crud_transactions.py / crud_service.py
                           — plain persistence, called only by the matching
                             *_server.py, never by agents.py directly
  database.py / models.py — SQLAlchemy engine/session, ORM models
  exceptions.py            — NotFoundError / InsufficientFundsError /
                              InvalidStatusTransitionError / ValidationError,
                              raised by servers, caught by agents
tests/                     — pytest, imports via "from bank_platform.x import y"
  (package is installed editable, so no pythonpath hack is needed)
```

## Architecture

```
main.py (/chat)
  → coordinator.py (routes on intent prefix)
    → agents.py (Accounts/Transaction/Service Agent)
      → interfaces.py: MCPClient.call_tool(tool_name, params)
        → accounts_server.py / transactions_server.py / service_server.py
          → crud_accounts.py / crud_transactions.py / crud_service.py
            → database.py / models.py → Postgres
```

- **MCP servers own their own data's invariants** (validation, atomicity,
  state transitions) — not the agents, and not the `crud_*` layer. This is
  deliberate: a real microservice validates at its own boundary rather than
  trusting its caller, so nothing that isn't `agents.py` could ever bypass
  these rules later. `crud_*` stays pure persistence, called only by its
  matching `*_server.py`.
- **Every MCP tool call is one atomic, self-contained DB transaction** — a
  session is opened, used, committed or rolled back, and closed inside a
  single tool call, never shared across two calls. This is what makes the
  in-process version behave like a real network-separated MCP call would.
- **No real MCP protocol/transport.** `InProcessMCPClient` (`interfaces.py`)
  dispatches `call_tool(name, params)` straight to a Python function in one
  of the three `*_server.py` modules — no subprocess, no JSON-RPC, no `mcp`
  dependency. This was a deliberate choice after weighing it directly against
  the real `mcp` SDK (see PROGRESS.md's change log): the SDK is async-only,
  which would ripple through agents/coordinator/endpoint/tests, and adds
  subprocess-management complexity (with Windows-specific risk for `stdio`)
  for zero functional gain while the only caller is our own Coordinator in
  the same process. The `MCPClient` interface is the seam that keeps this
  swappable later without touching agent code, once an external caller
  actually needs it.
- **No LLM yet.** Coordinator routing is a plain string-split + enum lookup,
  not an LLM call. Intentional for now, not a placeholder bug.
- **Money uses `Decimal`, not `float`,** for all balance/amount arithmetic
  inside the servers. `float()` conversion only happens when a server
  serializes its result to a plain dict for the response.
- **Error taxonomy:** `AgentResponse.error` is one of `invalid_intent`,
  `unknown_agent`, `unknown_operation`, `not_found`, `missing_field`,
  `insufficient_funds`, `invalid_status_transition`, `validation_error`.
  Domain exceptions (`exceptions.py`) are raised by the servers and caught
  per-agent in `agents.py` — never let one propagate to FastAPI's default
  500 handler.

## Running it

```bash
docker compose up -d          # Postgres 17, bank/bank@localhost:5432/bank_platform
uv sync                        # installs deps + bank_platform itself, editable
uv run python -c "from bank_platform.models import Base; from bank_platform.database import engine; Base.metadata.create_all(engine)"  # tables (no migration tool yet)
uv run fastapi dev src/bank_platform/main.py    # dev server
uv run pytest -v               # requires the DB container running, no mocking
```

Port 5432 is also used by an unrelated project (`fastapi-postgresql-learning`)
on this machine — check `docker ps -a` before assuming which container is up.

## Conventions

- Branch: `main` (not `master`).
- Commits: create new commits, don't amend; end messages with the
  `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` trailer.
- All internal imports inside `src/bank_platform/` are absolute and
  package-qualified (`from bank_platform.exceptions import ...`), never bare
  (`from exceptions import ...`) — bare imports break once installed as a
  package. `tests/` imports the same way.
- `crud_*` and `*_server.py` files are split one per domain (not shared
  single files), matching the agent split.
- When a real bug is found and fixed (not just a feature gap), add an entry
  to `PROBLEMS.md` using its template — problem, root cause, solution, why it
  mattered. When a phase/step completes or a design decision is made, update
  `PROGRESS.md`. Don't document inconsequential items in either file.
