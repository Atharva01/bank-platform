# Bank Platform — Phase Ledger

Tracks SDLC progress against the phase plan. Update status as work moves through each phase.

Status legend: `Not Started` | `In Progress` | `Blocked` | `Done`

| # | Phase | Status | Started | Completed | Notes |
|---|-------|--------|---------|-----------|-------|
| 0 | Contracts & Interfaces | Done | 2026-09-11 | 2026-09-11 | `AgentType`/`AgentRequest`/`AgentResponse`/`Agent` ABC in `agents.py`. `interfaces.py`'s `MCPClient`/`SessionStore` stubs written but not yet wired in |
| 1 | Agent Business Logic | Done | 2026-09-11 | 2026-09-11 | Rule-based Coordinator + Accounts/Transaction/Service Agents, full CRUD, 11 pytest tests passing. Built straight against Postgres instead of Phase 0 stubs — agents currently call `crud_*` directly, not through `MCPClient` |
| 2 | MCP Servers | Not Started | | | Retrofit: wrap existing `crud_accounts`/`crud_transactions`/`crud_service` behind the `MCPClient` interface so agents stop touching Postgres directly. Transport (real MCP protocol vs. in-process MCP-shaped interface) undecided |
| 3 | LLM Integration | Not Started | | | Self-Hosted + Third-party LLM behind a switchable interface |
| 4 | Session Store | Not Started | | | Conversation history + inter-agent shared state |
| 5 | PII Redaction | Not Started | | | Redaction between agents and LLM layer |
| 6 | Auth & Authorisation | Not Started | | | Bank identity provider + per-request authorisation |
| 7 | Edge Layer | Not Started | | | WAF, DDoS, rate limits, API Gateway |
| 8 | Observability & Cost Tracker | Not Started | | | Prompts/agent/tool call logging, resource metrics, cost aggregation |
| 9 | Agent Evaluation Suite | Not Started | | | Eval harness across both LLM backends, CI-gated |
| 10 | Integration & Hardening | Not Started | | | End-to-end tests, load testing, security review |

## Current Focus

**Phase 2 — MCP Servers.** Decision pending: real MCP protocol (stdio/SDK, 3 separate processes) vs. an in-process MCP-shaped `MCPClient` implementation that can be swapped for the real protocol later without touching agent code.

## Change Log

- 2026-09-11 — Ledger created. Phase plan agreed; Python stack, LLM-based Coordinator routing decided.
- 2026-09-11 — Phases 0 and 1 built in a CRUD-first detour (agents talk directly to Postgres, bypassing the MCP abstraction) to prove out agent coordination end-to-end before returning to the phased plan. Marked Done retroactively. Phase 2 is now the gap between current state and the original architecture diagram.
