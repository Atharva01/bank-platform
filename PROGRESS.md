# Bank Platform — Phase Ledger

Tracks SDLC progress against the phase plan. Update status as work moves through each phase.

Status legend: `Not Started` | `In Progress` | `Blocked` | `Done`

| # | Phase | Status | Started | Completed | Notes |
|---|-------|--------|---------|-----------|-------|
| 0 | Contracts & Interfaces | Done | 2026-09-11 | 2026-09-11 | `AgentType`/`AgentRequest`/`AgentResponse`/`Agent` ABC in `agents.py`. `interfaces.py`'s `MCPClient`/`SessionStore` stubs written but not yet wired in |
| 1 | Agent Business Logic | In Progress | 2026-09-11 | | CRUD passthrough done (13 pytest tests passing) but agents were thin proxies with no domain rules. Reopened to add real business logic before moving to Phase 2 — see plan in Current Focus below |
| 2 | MCP Servers | Not Started | | | Deferred until Phase 1's business logic is complete. Retrofit: wrap `crud_accounts`/`crud_transactions`/`crud_service` behind the `MCPClient` interface so agents stop touching Postgres directly. Each MCP server treated as a domain-owning microservice (own DB access, own process boundary eventually), not middleware — agents never see a DB session once retrofitted. Transport: start in-process (no real MCP protocol yet); if/when a real network boundary is needed, standard MCP transports (`stdio`, Streamable HTTP) preferred over non-standard WebSocket |
| 3 | LLM Integration | Not Started | | | Self-Hosted + Third-party LLM behind a switchable interface |
| 4 | Session Store | Not Started | | | Conversation history + inter-agent shared state |
| 5 | PII Redaction | Not Started | | | Redaction between agents and LLM layer |
| 6 | Auth & Authorisation | Not Started | | | Bank identity provider + per-request authorisation |
| 7 | Edge Layer | Not Started | | | WAF, DDoS, rate limits, API Gateway |
| 8 | Observability & Cost Tracker | Not Started | | | Prompts/agent/tool call logging, resource metrics, cost aggregation |
| 9 | Agent Evaluation Suite | Not Started | | | Eval harness across both LLM backends, CI-gated |
| 10 | Integration & Hardening | Not Started | | | End-to-end tests, load testing, security review |

## Current Focus

**Phase 1 (reopened) — give the agents real business logic before Phase 2 (MCP Servers).** Agreed plan, not yet implemented:

| Area | Decision |
|---|---|
| Balance linkage | `transaction.create` atomically updates `Account.balance` |
| Overdraft | Blocked — a debit that would take balance negative returns `insufficient_funds` |
| Transaction direction | Signed `amount` (positive = credit, negative = debit) — no separate `type` field |
| Service status | State machine: `pending → approved/rejected`, `approved → completed`; `completed`/`rejected` are terminal |
| Atomicity | `crud_*` functions stop auto-committing (`add`/`flush` only); the agent commits once per `handle()` call and rolls back on rule failure |
| New validations | Reject negative `balance` / empty `owner_name` on account create; `request_type` restricted to `change_of_address` / `cheque_book_request` / `kyc_update` |
| New error codes | `insufficient_funds`, `invalid_status_transition`, `validation_error` |
| Bug to fix alongside | `transaction.create` currently never checks that `account_id` refers to a real account |
| Money type | Balance/amount arithmetic switches from Python `float` to `Decimal` to avoid precision drift; Postgres columns already `Numeric(12,2)`, this is a Python-side-only fix |

**Tech stack for this work:** plain Python classes for agents (no LangGraph/CrewAI/AutoGen — not worth the indirection until Phase 3 needs LLM reasoning loops); hand-rolled dict for the service status state machine (4 states, not worth a library like `transitions`); Pydantic continues to own input shape validation, business rules stay as plain `if` checks in each agent.

**Implementation order:** (1) ✅ crud commit refactor → (2) ✅ TransactionAgent balance/overdraft logic with Decimal math → (3) ServiceAgent status machine → (4) input validation on creates → (5) tests for all of the above, including new error paths.

Once this lands, Phase 1 moves to `Done` and Phase 2 (MCP Servers) resumes — retrofitting these same `crud_*` functions behind the `MCPClient` interface without changing agent code.

## Change Log

- 2026-09-11 — Ledger created. Phase plan agreed; Python stack, LLM-based Coordinator routing decided.
- 2026-09-11 — Phases 0 and 1 built in a CRUD-first detour (agents talk directly to Postgres, bypassing the MCP abstraction) to prove out agent coordination end-to-end before returning to the phased plan. Marked Done retroactively. Phase 2 is now the gap between current state and the original architecture diagram.
- 2026-09-11 — Reopened Phase 1: CRUD passthrough alone isn't real agent business logic. Agreed a plan (balance linkage, overdraft rule, service status machine, input validation, atomic commits) before moving on to Phase 2.
- 2026-09-11 — Discussed tech stack for the business-logic work: plain Python classes (no agent framework yet), hand-rolled state machine, and switching balance/amount math from float to Decimal to avoid precision drift.
- 2026-09-11 — Discussed MCP server design ahead of Phase 2: each MCP server is a domain-owning microservice (not middleware) that will own its own DB access once retrofitted. Agreed each logical write should be one composite crud_* function (e.g. `create_transaction_and_update_balance`), not multiple functions orchestrated by the agent, so it maps cleanly onto a single future MCP tool call and stays atomic. Transport: in-process first; real MCP later via stdio/Streamable HTTP, not WebSocket.
