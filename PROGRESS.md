# Bank Platform — Phase Ledger

Tracks SDLC progress against the phase plan. Update status as work moves through each phase.
See [PROBLEMS.md](PROBLEMS.md) for the log of real issues hit and how they were solved.

Status legend: `Not Started` | `In Progress` | `Blocked` | `Done`

| # | Phase | Status | Started | Completed | Notes |
|---|-------|--------|---------|-----------|-------|
| 0 | Contracts & Interfaces | Done | 2026-09-11 | 2026-09-11 | `AgentType`/`AgentRequest`/`AgentResponse`/`Agent` ABC in `agents.py`. `interfaces.py`'s `MCPClient`/`SessionStore` stubs written but not yet wired in |
| 1 | Agent Business Logic | Done | 2026-09-11 | 2026-09-11 | Real business logic added: atomic balance-linked transactions with overdraft protection, service request status state machine, input validation on account/service creation. Decimal used for money math. 32 pytest tests passing. See Change Log for the full plan that was implemented |
| 2 | MCP Servers | Not Started | | | Retrofit: wrap `crud_accounts`/`crud_transactions`/`crud_service` behind the `MCPClient` interface so agents stop touching Postgres directly. Each MCP server treated as a domain-owning microservice (own DB access, own process boundary eventually), not middleware — agents never see a DB session once retrofitted. Transport: start in-process (no real MCP protocol yet); if/when a real network boundary is needed, standard MCP transports (`stdio`, Streamable HTTP) preferred over non-standard WebSocket |
| 3 | LLM Integration | Not Started | | | Self-Hosted + Third-party LLM behind a switchable interface |
| 4 | Session Store | Not Started | | | Conversation history + inter-agent shared state |
| 5 | PII Redaction | Not Started | | | Redaction between agents and LLM layer |
| 6 | Auth & Authorisation | Not Started | | | Bank identity provider + per-request authorisation |
| 7 | Edge Layer | Not Started | | | WAF, DDoS, rate limits, API Gateway |
| 8 | Observability & Cost Tracker | Not Started | | | Prompts/agent/tool call logging, resource metrics, cost aggregation |
| 9 | Agent Evaluation Suite | Not Started | | | Eval harness across both LLM backends, CI-gated |
| 10 | Integration & Hardening | Not Started | | | End-to-end tests, load testing, security review |

## Current Focus

**Phase 2 — MCP Servers.** Plan agreed, not yet implemented.

**Ownership principle (refined from the earlier "business rules live in the agent" framing):**
MCP servers own all invariants about their own data — atomicity, valid values,
valid state transitions — the same way any real microservice validates at its
own boundary rather than trusting the caller. Agents shrink to: parse intent →
translate `payload` into tool-call arguments → call `MCPClient` → map the
tool's result/exception to an `AgentResponse`. Concretely, this moves the
input validation and the service status state machine (both currently in
`agents.py`) into the MCP servers.

| Server | Owns | Tools / business logic inside |
|---|---|---|
| Accounts server | `Account` table | `create_account`/`update_account` validate `owner_name`/`balance` (moved from `AccountsAgent`); `get_account`, `delete_account` |
| Transactions server | `Transaction` table + `Account.balance` | `create_transaction` keeps the atomic overdraft-protected write; **`update_transaction`/`delete_transaction` now also atomically re-adjust `Account.balance`** (reverse the old amount's effect, apply the new one) — closes the previously-flagged gap where editing/deleting a transaction left balance stale; `get_transaction`, `list_transactions` |
| Service server | `ServiceRequest` table | `create_service_request` validates `request_type` (moved from `ServiceAgent`); `update_service_request` enforces the status state machine (moved from `ServiceAgent`); `get_service_request`, `delete_service_request` |

**Transport:** in-process for now (no real MCP protocol/process boundary yet), one DB session per tool call, never shared across two tool calls — matches how a real network-separated MCP call would behave, and is why the service-status check becomes a read-then-decide pattern across two tool calls instead of one shared transaction.

**Implementation shape:** three server modules (`accounts_server.py`, `transactions_server.py`, `service_server.py`) wrapping the existing `crud_*` functions plus the validation/state-machine logic pulled out of `agents.py`; a concrete `MCPClient` implementation in `interfaces.py` dispatching `call_tool(domain, tool_name, params)` to the right server; `agents.py` rewritten to call the client instead of importing `crud_*`/`SessionLocal` directly.

## Change Log

- 2026-09-11 — Ledger created. Phase plan agreed; Python stack, LLM-based Coordinator routing decided.
- 2026-09-11 — Phases 0 and 1 built in a CRUD-first detour (agents talk directly to Postgres, bypassing the MCP abstraction) to prove out agent coordination end-to-end before returning to the phased plan. Marked Done retroactively. Phase 2 is now the gap between current state and the original architecture diagram.
- 2026-09-11 — Reopened Phase 1: CRUD passthrough alone isn't real agent business logic. Agreed a plan (balance linkage, overdraft rule, service status machine, input validation, atomic commits) before moving on to Phase 2.
- 2026-09-11 — Discussed tech stack for the business-logic work: plain Python classes (no agent framework yet), hand-rolled state machine, and switching balance/amount math from float to Decimal to avoid precision drift.
- 2026-09-11 — Discussed MCP server design ahead of Phase 2: each MCP server is a domain-owning microservice (not middleware) that will own its own DB access once retrofitted. Agreed each logical write should be one composite crud_* function (e.g. `create_transaction_and_update_balance`), not multiple functions orchestrated by the agent, so it maps cleanly onto a single future MCP tool call and stays atomic. Transport: in-process first; real MCP later via stdio/Streamable HTTP, not WebSocket.
- 2026-09-11 — Implemented step 2 (atomic balance-linked transaction writes with overdraft protection, Decimal math), step 3 (service status state machine), and step 4 (input validation on account/service creation). Phase 1 marked Done. 32 pytest tests passing. Phase 2 (MCP Servers) is now current focus.
- 2026-09-11 — Planned Phase 2 in detail. Refined the ownership principle: MCP servers own their own data invariants (validation + atomicity + state transitions) rather than trusting the caller, so input validation and the status state machine move from `agents.py` into the MCP servers. Also decided transaction.update/delete will atomically re-adjust Account.balance once the Transactions server formally owns that invariant, closing a previously-flagged gap.
