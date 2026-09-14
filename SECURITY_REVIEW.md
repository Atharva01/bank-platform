# Security Review (Phase 10, part 1)

Grounded in the official
[OWASP API Security Top 10 (2023)](https://api-security.owasp.org/editions/2023/en/0x11-t10) —
this app is fundamentally an API (REST + `/chat`), so that's the
established framework this review is audited against, not an improvised
checklist. One entry per category: what was checked, its status, and why.

Dated 2026-09-14. Re-run this review (or at least re-check any
"Confirmed safe" entry touching code that changed) whenever auth,
ownership, or a new customer-facing field is added.

---

## API1:2023 — Broken Object Level Authorization

**Status: Confirmed safe.** Every REST endpoint that takes an
`account_id`/`transaction_id`/`request_id` calls `authz.require_owner()`
or a thin wrapper around it (`_require_owns_transaction`,
`_require_owns_request`) before touching the resource — verified by
reading every route in `accounts_router.py`/`transactions_router.py`/
`service_router.py`, not a sample. The chat-tool path uses the
equivalent `authz.owner_guard()` decorator (`accounts_tools.py`/
`transactions_tools.py`/`service_tools.py`), sourcing `customer_id` from
the request's own JWT via `RunnableConfig` injection — never from
anything the LLM supplies. `require_owner` deliberately raises the same
`NotFoundError` whether the resource doesn't exist or isn't the caller's
(standard IDOR mitigation, documented in `authz.py`'s own docstring).

## API2:2023 — Broken Authentication

**Status: Mostly confirmed safe, two minor gaps backlogged.**
- Login is enumeration-safe: unknown-username and wrong-password return
  the identical error (`auth.py`'s `authenticate_customer`/
  `authenticate_staff_user`).
- JWTs carry a `"typ"` claim (`staff`/`customer`) so one token kind can
  never pass the other's dependency — a leaked/reused token from one
  identity can't cross into the other.
- Token expiry (60 minutes) is reasonable for this app's scope.
- **Gap (low):** password policy is minimum-length only (8 characters,
  `customer_router.py`), no maximum. bcrypt silently truncates input
  past 72 bytes — not exploitable today (nothing this app does depends
  on password length beyond that), but worth a maximum-length check so
  a very long password doesn't silently collapse to a shorter effective
  one. **Backlogged, not fixed.**
- **Gap (low):** `JWT_SECRET_KEY` has no startup-time strength/length
  validation — a weak or short value in `.env` would silently work.
  **Backlogged, not fixed.**

## API3:2023 — Broken Object Property Level Authorization

**Status: Critical finding, fixed this review.** `PATCH /api/accounts/{id}`
and the chat `update_account` tool both accepted a `balance` field and
wrote it directly onto `Account.balance`, bypassing
`transactions_server.py`'s atomic, ledger-linked balance adjustment
entirely. Any customer could set their own balance to anything. Fixed:
`balance` removed from both the REST request model and the chat tool's
schema; `ACCOUNTS_AGENT_PROMPT` updated to explain deposits/withdrawals
are the only path. See `PROBLEMS.md` #26 for the full writeup, root
cause, and live verification.

## API4:2023 — Unrestricted Resource Consumption

**Status: Partially mitigated, one gap backlogged.**
- Rate limiting exists (`slowapi`, `rate_limit.py`): 5/minute on
  auth/registration endpoints, 20/minute on `/api/chat` — already
  documented as in-memory/per-process only (Phase 7's known limitation,
  addressed at the edge by Traefik's rate-limit middleware once
  deployed, see `CLAUDE.md`'s "Deploying" section).
- LLM calls are capped (`llm.py`'s `max_tokens`), preventing an
  unbounded-cost single response.
- Per-thread idempotency (`tool_utils.idempotent`) prevents a duplicate
  `create_*` call from the same conversation thread.
- **Gap (moderate):** no request body size limit exists anywhere — not
  in the FastAPI app, not in Traefik's config
  (`docker-compose.prod.yml`). A large JSON payload to any POST/PATCH
  endpoint isn't rejected before being fully parsed. **Backlogged, not
  fixed** — needs either a Starlette middleware or a Traefik
  `buffering`/body-size middleware, worth doing alongside any future
  edge-layer hardening pass rather than as an isolated patch.

## API5:2023 — Broken Function Level Authorization

**Status: Confirmed safe, one policy question backlogged (not a
vulnerability).** Staff-only actions — `DELETE /api/accounts/{id}` and
`PATCH /api/staff/service-requests/{id}/status` — are gated by
`Depends(get_current_staff_user)`, structurally unreachable by a
customer token (different JWT `"typ"`, see API2). No customer-facing
endpoint or chat tool can reach either.

- **Note (not a bug):** customers *can* `DELETE` their own transactions
  and service requests via REST — deleting a transaction correctly
  reverses its balance effect atomically (`transactions_server.py`), so
  it's not a balance-integrity issue, but letting a customer erase their
  own transaction history is a real business-policy question (audit
  trail integrity) worth a deliberate decision, not a silent allowance.
  **Backlogged as a discussion item**, not fixed unilaterally here.

## API6:2023 — Unrestricted Access to Sensitive Business Flows

**Status: Confirmed adequate for current scope.** The combination of
per-thread idempotency (blocks a duplicate create within one
conversation) and per-IP rate limiting (blocks rapid-fire abuse across
requests) covers the realistic abuse vectors today — account creation,
deposits, and service requests all sit behind both. Revisit if a flow
with real fraud potential (e.g. automated account opening at scale) is
added later.

## API7:2023 — Server Side Request Forgery

**Status: Not applicable.** This app never fetches a remote resource at
a user-supplied URL — no webhook registration, no "fetch this link"
feature anywhere in the codebase. Quick check only, as scoped.

## API8:2023 — Security Misconfiguration

**Status: Mostly confirmed safe, one gap backlogged.**
- CORS defaults to `*` for local dev (frontend on a different port),
  configurable via `FRONTEND_ORIGIN` for production — already
  documented as intentional (Phase 7).
- Debug mode is off (`FastAPI(lifespan=lifespan)`, no `debug=True`) —
  confirmed no stack traces leak to a client on an unhandled error.
- Error responses are fully controlled: `main.py`'s global exception
  handlers map `exceptions.py`'s domain exceptions to `{detail,
  error_type}` — no raw exception internals ever returned.
- **Gap (moderate):** `/docs` and `/openapi.json` are publicly exposed
  with no auth (verified live: both return 200 to an unauthenticated
  request). This doesn't bypass any authorization itself, but it hands
  an unauthenticated caller the full API surface — including the
  staff-only endpoint paths — for free reconnaissance. **Backlogged, not
  fixed** — the fix is a one-line `FastAPI(docs_url=None,
  openapi_url=None)` gated by an environment flag for production, kept
  open for local dev; worth doing alongside a real deployment rather
  than half-done here.

## API9:2023 — Improper Inventory Management

**Status: Confirmed safe.** Every route in the app was reviewed as part
of API1/API5's pass above — all are intentional and already documented
in `CLAUDE.md`. No forgotten debug/test-only endpoint was found. (The
`/docs`/`/openapi.json` exposure is recorded under API8 above, since
it's a configuration choice rather than an undocumented endpoint.)

## API10:2023 — Unsafe Consumption of APIs

**Status: Confirmed safe by design.** This app's one external API
dependency is the LLM provider (Muse Spark). Its tool-call *arguments*
are never trusted for identity: `authz.owner_guard`/`inject_customer_id`
always source `customer_id` from the caller's own JWT via
`RunnableConfig` injection, never from anything the model supplies in a
tool call — confirmed via `authz.py`'s design (built and empirically
verified against LangChain's actual schema-inference behavior earlier
this project, see `PROGRESS.md`'s 2026-09-12 entry). The LLM can choose
*which* tool to call and *what* non-identity arguments to pass, but can
never forge who it's acting as.

---

## Summary

| # | Category | Status |
|---|---|---|
| API1 | Broken Object Level Authorization | Confirmed safe |
| API2 | Broken Authentication | Mostly safe — 2 low gaps backlogged |
| API3 | Broken Object Property Level Authorization | **Critical — fixed this review** |
| API4 | Unrestricted Resource Consumption | Partial — 1 moderate gap backlogged |
| API5 | Broken Function Level Authorization | Confirmed safe — 1 policy question backlogged |
| API6 | Unrestricted Access to Sensitive Business Flows | Confirmed adequate |
| API7 | Server Side Request Forgery | Not applicable |
| API8 | Security Misconfiguration | Mostly safe — 1 moderate gap backlogged |
| API9 | Improper Inventory Management | Confirmed safe |
| API10 | Unsafe Consumption of APIs | Confirmed safe by design |

**Explicitly out of scope for this pass** (see `PROGRESS.md`'s Phase 10
row): dependency CVE scanning (needs a real tool like `pip-audit` run
and reviewed — a real follow-up, not silently skipped); end-to-end tests
and load testing (separate, not-yet-started parts of Phase 10); the
AWS/Traefik edge-layer security posture (already covered in Phase 7's
own design work, see `CLAUDE.md`'s "Deploying" section).
