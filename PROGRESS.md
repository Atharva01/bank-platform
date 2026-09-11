# Bank Platform — Phase Ledger

Tracks SDLC progress against the phase plan. Update status as work moves through each phase.
See [PROBLEMS.md](PROBLEMS.md) for the log of real issues hit and how they were solved.

Status legend: `Not Started` | `In Progress` | `Blocked` | `Done`

| # | Phase | Status | Started | Completed | Notes |
|---|-------|--------|---------|-----------|-------|
| 0 | Contracts & Interfaces | Done | 2026-09-11 | 2026-09-11 | `AgentType`/`AgentRequest`/`AgentResponse`/`Agent` ABC in `agents.py`. `interfaces.py`'s `MCPClient`/`SessionStore` stubs written but not yet wired in |
| 1 | Agent Business Logic | Done | 2026-09-11 | 2026-09-11 | Real business logic added: atomic balance-linked transactions with overdraft protection, service request status state machine, input validation on account/service creation. Decimal used for money math. 32 pytest tests passing. See Change Log for the full plan that was implemented |
| 2 | MCP Servers | Done | 2026-09-11 | 2026-09-11 | `accounts_server.py`/`transactions_server.py`/`service_server.py` now own their data + invariants (validation, atomicity, status state machine — moved out of `agents.py`). `InProcessMCPClient` in `interfaces.py` dispatches `call_tool(name, params)`. Agents no longer touch Postgres/SessionLocal at all. Also closed a gap: transaction update/delete now atomically re-adjust Account.balance. 36 pytest tests passing, verified over real HTTP. Transport is in-process (no subprocess/real MCP protocol) — deliberate, see Change Log |
| 3 | LLM Integration | Not Started | | | Self-Hosted + Third-party LLM behind a switchable interface |
| 4 | Session Store | Not Started | | | Conversation history + inter-agent shared state |
| 5 | PII Redaction | Not Started | | | Redaction between agents and LLM layer |
| 6 | Auth & Authorisation | Not Started | | | Bank identity provider + per-request authorisation |
| 7 | Edge Layer | Not Started | | | WAF, DDoS, rate limits, API Gateway |
| 8 | Observability & Cost Tracker | Not Started | | | Prompts/agent/tool call logging, resource metrics, cost aggregation |
| 9 | Agent Evaluation Suite | Not Started | | | Eval harness across both LLM backends, CI-gated |
| 10 | Integration & Hardening | Not Started | | | End-to-end tests, load testing, security review |

## Current Focus

**Phase 3 — LLM Integration.** Not started. Phase 2 (MCP Servers) is complete — see row above for what shipped.

## Change Log

- 2026-09-11 — Ledger created. Phase plan agreed; Python stack, LLM-based Coordinator routing decided.
- 2026-09-11 — Phases 0 and 1 built in a CRUD-first detour (agents talk directly to Postgres, bypassing the MCP abstraction) to prove out agent coordination end-to-end before returning to the phased plan. Marked Done retroactively. Phase 2 is now the gap between current state and the original architecture diagram.
- 2026-09-11 — Reopened Phase 1: CRUD passthrough alone isn't real agent business logic. Agreed a plan (balance linkage, overdraft rule, service status machine, input validation, atomic commits) before moving on to Phase 2.
- 2026-09-11 — Discussed tech stack for the business-logic work: plain Python classes (no agent framework yet), hand-rolled state machine, and switching balance/amount math from float to Decimal to avoid precision drift.
- 2026-09-11 — Discussed MCP server design ahead of Phase 2: each MCP server is a domain-owning microservice (not middleware) that will own its own DB access once retrofitted. Agreed each logical write should be one composite crud_* function (e.g. `create_transaction_and_update_balance`), not multiple functions orchestrated by the agent, so it maps cleanly onto a single future MCP tool call and stays atomic. Transport: in-process first; real MCP later via stdio/Streamable HTTP, not WebSocket.
- 2026-09-11 — Implemented step 2 (atomic balance-linked transaction writes with overdraft protection, Decimal math), step 3 (service status state machine), and step 4 (input validation on account/service creation). Phase 1 marked Done. 32 pytest tests passing. Phase 2 (MCP Servers) is now current focus.
- 2026-09-11 — Planned Phase 2 in detail. Refined the ownership principle: MCP servers own their own data invariants (validation + atomicity + state transitions) rather than trusting the caller, so input validation and the status state machine move from `agents.py` into the MCP servers. Also decided transaction.update/delete will atomically re-adjust Account.balance once the Transactions server formally owns that invariant, closing a previously-flagged gap.
- 2026-09-11 — Considered adopting the real `mcp` SDK (FastMCP, stdio/in-memory transport) instead of hand-rolling. Decided against it for now: the SDK is async-only, which would ripple through agents/coordinator/endpoint/tests, plus subprocess management adds real complexity (and Windows-specific risk for stdio) for zero functional gain while the only caller is our own Coordinator in the same process. The `MCPClient` interface is the seam that keeps this swappable later without touching agent code, once an external caller actually exists — deferred, not rejected.
- 2026-09-11 — Implemented Phase 2: three MCP server modules now own their domain's data and invariants; `InProcessMCPClient` dispatches tool calls; agents.py no longer touches Postgres/SessionLocal at all. Closed the transaction-edit/delete balance-staleness gap in the same pass. 36 tests passing, verified over real HTTP. Phase 2 marked Done.
- 2026-09-11 — Restructured the project: all root-level modules moved into `src/bank_platform/` as a real installable package (hatchling build backend, `uv sync` installs it editable), replacing scattered root files. All internal imports rewritten to package-qualified (`from bank_platform.x import y`). Tests updated the same way. 36 tests still passing, verified over real HTTP against the new layout.
