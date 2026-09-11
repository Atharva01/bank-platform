# Bank Platform — Phase Ledger

Tracks SDLC progress against the phase plan. Update status as work moves through each phase.

Status legend: `Not Started` | `In Progress` | `Blocked` | `Done`

| # | Phase | Status | Started | Completed | Notes |
|---|-------|--------|---------|-----------|-------|
| 0 | Contracts & Interfaces | Not Started | | | Shared agent message schema, `Agent` base interface, stub MCP/session interfaces |
| 1 | Agent Business Logic | Not Started | | | Coordinator (LLM-routed) + Accounts/Transaction/Service Agents, built against Phase 0 stubs |
| 2 | MCP Servers | Not Started | | | Accounts, Transactions, Service MCP servers with real tool implementations |
| 3 | LLM Integration | Not Started | | | Self-Hosted + Third-party LLM behind a switchable interface |
| 4 | Session Store | Not Started | | | Conversation history + inter-agent shared state |
| 5 | PII Redaction | Not Started | | | Redaction between agents and LLM layer |
| 6 | Auth & Authorisation | Not Started | | | Bank identity provider + per-request authorisation |
| 7 | Edge Layer | Not Started | | | WAF, DDoS, rate limits, API Gateway |
| 8 | Observability & Cost Tracker | Not Started | | | Prompts/agent/tool call logging, resource metrics, cost aggregation |
| 9 | Agent Evaluation Suite | Not Started | | | Eval harness across both LLM backends, CI-gated |
| 10 | Integration & Hardening | Not Started | | | End-to-end tests, load testing, security review |

## Current Focus

**Phase 0 → Phase 1** — defining the shared agent contract, then building the Coordinator and three domain agents against stubs.

## Change Log

- 2026-09-11 — Ledger created. Phase plan agreed; Python stack, LLM-based Coordinator routing decided.
