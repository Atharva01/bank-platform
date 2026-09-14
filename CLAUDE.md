# bank-platform

Multi-agent banking assistant, originally built against a reference
architecture diagram
(`assets\ad3ccd54-9532-4b2b-b8f9-b837caf40af1_image.png`, "Step 14: Edge
Layer Security") and now implementing nearly all of it: a LangGraph
supervisor routes `/chat` to one of three specialist agents (Accounts,
Transaction, Service), each backed by its own MCP-style domain server on
Postgres, plus real customer/staff auth, PII redaction, an edge layer
(Traefik + AWS/Terraform), observability, and an on-demand agent
evaluation suite. See "Architecture" below for the real current shape.

**Always check [PROGRESS.md](PROGRESS.md) first** — it's the authoritative
phase ledger (what's done, what's in progress, the agreed plan for current
work) and is kept up to date every session. **Check [PROBLEMS.md](PROBLEMS.md)**
for real issues already hit and how they were solved, before re-diagnosing
something that's been through this before.

## Stack

Python (>=3.13), FastAPI, SQLAlchemy 2.0, Postgres 17 via Docker, `psycopg`
(v3, not psycopg2), `uv` for dependency management, `pytest` (no mocking —
real DB), `hatchling` as the build backend (src layout, installed editable
via `uv sync`). LangGraph + `langgraph-supervisor` for agent orchestration,
`langchain_openai.ChatOpenAI` (OpenAI-compatible shape) as the LLM client —
see `llm.py`'s docstring and PROBLEMS.md for the provider evaluation trail
(Ollama → DeepSeek → Groq → Meta Muse Spark, the current active provider).
No real MCP protocol (`mcp`/FastMCP) — domain servers are in-process
Python calls, not a separate service; see the Architecture section below
for why.

## Layout

```
src/bank_platform/       — the package; all internal imports are
                            "from bank_platform.x import y" (absolute, never
                            relative or bare)
  main.py                    — FastAPI app: /api/chat + every REST router,
                                 session-sweep background task, CORS,
                                 domain-exception → HTTP status mapping
  graph.py                   — LangGraph supervisor + 3 specialist agents
                                 (create_agent() per domain), session/
                                 customer binding, PII sanitize/detokenize,
                                 observability callback wiring
  llm.py                     — shared ChatOpenAI client (provider-swappable)
  accounts_tools.py / transactions_tools.py / service_tools.py
                              — LangChain StructuredTool wrappers around the
                                domain servers below - the only files that
                                import LangChain for their domain. Wrap
                                tools with authz.owner_guard/inject_customer_id,
                                pii_guard.pii_guard, tool_utils.idempotent
  accounts_server.py         — MCP-style domain server: owns Account +
                                 its validation
  transactions_server.py     — owns Transaction + Account.balance (the
                                 only server spanning two tables)
  service_server.py          — owns ServiceRequest + its status state
                                 machine
  crud_accounts.py / crud_transactions.py / crud_service.py
                              — plain persistence, called only by the
                                matching *_server.py
  accounts_router.py / transactions_router.py / service_router.py
                              — REST endpoints, no LLM in the loop, real
                                HTTP status codes (404/400/409/422)
  auth.py / auth_router.py    — staff login (JWT, typ: staff)
  customer_router.py          — customer self-service register/login
                                 (JWT, typ: customer)
  authz.py                    — ownership enforcement: require_owner (REST),
                                 owner_guard/inject_customer_id (chat tools)
  pii_guard.py                — reversible tokenization of Account.owner_name
                                 before it reaches the LLM
  session_store.py            — Postgres-backed session/customer binding
                                 (interfaces.py's SessionStore ABC, for real)
  observability.py / observability_router.py
                              — AgentEventLog + staff-only usage endpoint
  rate_limit.py                — shared slowapi Limiter (in-app rate limiting)
  tool_utils.py                — tool_safe (domain exception → ToolException)
                                 and idempotent (per-thread create_* dedup)
  interfaces.py                 — SessionStore ABC (session_store.py's base)
  database.py / models.py      — SQLAlchemy engine/session, ORM models
  exceptions.py                 — NotFoundError / InsufficientFundsError /
                                  InvalidStatusTransitionError /
                                  ValidationError / SessionOwnershipError,
                                  raised by servers, caught by
                                  main.py's global handlers (REST) or
                                  surfaced conversationally (chat)
tests/                     — pytest, imports via "from bank_platform.x import y"
  (package is installed editable, so no pythonpath hack is needed)
eval/                      — on-demand Agent Evaluation Suite (Phase 9) -
  deliberately outside tests/, never collected by pytest/CI; makes real
  paid LLM calls, run manually via `uv run python eval/run_eval.py`
infra/                     — Terraform (AWS EC2 deployment target, Phase 7)
```

`agents.py`/`coordinator.py`/`admin_auth.py` from the original Phase 0-2
design are gone entirely — replaced by `graph.py`'s LangGraph supervisor
(Phase 3) and real staff/customer auth (Phase 6).

## Architecture

```
main.py
  → /api/chat: ChatRequest{session_id, message} → ChatResponse{reply}   [conversational, always 200,
       → graph.py: run() → sanitize_incoming() → supervisor.invoke()      gated by customer auth]
            → LangGraph supervisor (thread_id = session_id, PostgresSaver checkpointer)
                 → accounts_agent / transaction_agent / service_agent (create_agent() per domain)
                      → accounts_tools.py / transactions_tools.py / service_tools.py
                           → owner_guard (ownership) / pii_guard (tokenize owner_name) / idempotent
  → /api/accounts, /api/transactions, /api/service-requests,           [deterministic REST, no LLM,
     /api/auth, /api/customers, /api/observability                      real 404/400/409/422,
       → accounts_router.py / transactions_router.py / service_router.py  gated by customer or staff auth]
            → authz.require_owner() → global exception handlers map exceptions.py → HTTP status
                                     |
                                     v  (both /chat and REST converge here)
                      accounts_server.py / transactions_server.py / service_server.py
                           → crud_*.py → database.py / models.py → Postgres
```

- **Domain servers own their own data's invariants** (validation,
  atomicity, state transitions) — not the agents, not the tool wrappers,
  and not the `crud_*` layer. They're framework-agnostic (no LangChain
  import) — only the matching `*_tools.py` file wraps them for the LLM.
  `crud_*` stays pure persistence, called only by its matching
  `*_server.py`.
- **Every domain-server call is one atomic, self-contained DB
  transaction** — a session is opened, used, committed or rolled back,
  and closed inside a single call, never shared across two.
- **No real MCP protocol/transport.** Domain servers are dispatched to
  directly as Python function calls — no subprocess, no JSON-RPC, no
  `mcp` dependency. Deliberate: the only callers are `graph.py`'s tool
  wrappers and the REST routers, both in the same process; nothing
  external needs a real MCP transport yet.
- **REST bypasses the LLM entirely** — `/api/accounts` etc. call the same
  domain-server functions `/chat`'s tools do, directly, with real HTTP
  status codes. `/chat` is not the only way in, and REST correctness
  never depends on the LLM behaving.
- **Auth is enforced identically on both paths** — `authz.py`'s
  `require_owner()` (REST, explicit `customer_id` from
  `Depends(get_current_customer)`) and `owner_guard()`/`inject_customer_id()`
  (chat tools, `customer_id` injected via `RunnableConfig` so the LLM
  never sees or supplies it) share the same underlying ownership check.
  Staff-only actions (account closure, service-request status changes)
  are REST-only — no chat tool can reach them.
- **Money uses `Decimal`, not `float`,** for all balance/amount
  arithmetic inside the servers. `float()` conversion only happens when
  a server serializes its result to a plain dict for the response.
- **Error taxonomy:** `exceptions.py`'s domain exceptions are raised by
  the servers. On the REST path, `main.py`'s global exception handlers
  map them to real HTTP status codes with a machine-readable
  `error_type`. On the chat path, `tool_utils.tool_safe` converts them to
  `ToolException`s so the agent can react conversationally — a domain
  exception must never propagate past either boundary uncaught (see
  PROBLEMS.md #22 for a real regression of this rule and its fix).

## Running it

```bash
docker compose up -d          # Postgres 17, bank/bank@localhost:5432/bank_platform
uv sync                        # installs deps + bank_platform itself, editable
uv run python -c "from bank_platform.models import Base; from bank_platform.database import engine; Base.metadata.create_all(engine)"  # tables (no migration tool yet)
uv run fastapi dev src/bank_platform/main.py    # dev server
uv run pytest -v               # requires the DB container running, no mocking
```

Set `MUSE_API_KEY`/`GROQ_API_KEY`/`JWT_SECRET_KEY` etc. in `.env` first —
see `.env.example` for the full list; `llm.py` reads its API key eagerly
at import time, so the backend won't even start without it.

After editing anything under `src/bank_platform/`, fully kill any running
`python.exe` processes and cold-start `fastapi dev` rather than trusting
`--reload` — a previously diagnosed, reconfirmed-multiple-times bug on
this dev setup (see PROBLEMS.md).

Port 5432 is also used by an unrelated project (`fastapi-postgresql-learning`)
on this machine — check `docker ps -a` before assuming which container is up.

To evaluate the live model's actual routing/tool-call behavior (not just
run the deterministic test suite), see `eval/README.md` — on-demand only,
costs real LLM calls.

## Deploying

Real deployment target: a bare VPS, self-managed Docker Compose, fronted by
**Traefik** (Phase 7 — Edge Layer). Reference architecture followed: FastAPI's
own official
[`full-stack-fastapi-template`](https://github.com/fastapi/full-stack-fastapi-template)
— an external `traefik-public` Docker network shared between Traefik and the
app services, single-domain path-based routing (frontend at the domain root,
every backend route under `/api` — same-origin, no CORS needed in
production), Docker-provider label-based routing with explicit per-service
opt-in.

```bash
docker network create traefik-public   # one-time, before first deploy
# Set DOMAIN and ACME_EMAIL in .env (real values — .env.example has
# placeholders), then:
docker compose -f docker-compose.prod.yml up -d
```

`docker-compose.prod.yml` is additive — `docker-compose.yml` stays the
local-dev, Postgres-only file described above, unchanged and still used for
local dev alongside `fastapi dev`. The prod compose file builds the backend
from this repo's own `Dockerfile` (via `fastapi run`, not `fastapi dev`) and
the frontend from `../bank-platform-ui` (assumes the two repos are checked
out side by side, matching local dev). `db` and `backend` publish no host
ports in the prod stack — Traefik is the only public entry point.

**Known limitation, not yet worked around:** the Traefik Docker-provider
routing above could not be verified end-to-end locally on Windows/Docker
Desktop — Traefik's own Docker client fails against Docker Desktop's socket-
forwarding layer with `Failed to retrieve information of the docker client
and server host` (confirmed the socket mount itself is fine: a plain `docker
info` through the identical mount succeeds; the incompatibility is specific
to Traefik's client library, not the mount). Real Let's Encrypt TLS
similarly can't be tested without the real domain. Both need verifying for
real on the actual VPS (a real Linux Docker host) before trusting this in
production — see PROBLEMS.md.

Explicitly out of scope so far: true DDoS mitigation (needs something in
front of the VPS itself, e.g. Cloudflare, once a DNS provider is chosen);
full WAF (CrowdSec/ModSecurity); a real secrets manager for `.env`'s
contents; horizontal backend scaling (Traefik's routing doesn't block adding
replicas later, but none are set up now).

### Cloud target: AWS EC2, provisioned via Terraform

The "bare VPS" above is concretely **AWS EC2** — same Docker Compose/Traefik
stack, unchanged, just hosted on an AWS-provisioned VM instead of a
generic self-managed server. `infra/` (new, Terraform, official
[`hashicorp/aws`](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
provider) declares the VM and everything AWS-specific around it:

- **Instance**: Amazon Linux 2023, `t4g.small` (Graviton/ARM — cheaper
  than the x86 equivalent, nothing in this stack requires x86), looked up
  by AMI name filter (not a hardcoded AMI ID that goes stale). 30GB gp3
  root volume — AL2023's 8GB default is too small once Docker images,
  Postgres data, and Traefik's ACME certs are all on it.
- **Security group**: only 80/443 inbound from `0.0.0.0/0` — matches the
  Traefik design exactly. **No inbound port 22.** Shell access is via
  **AWS Systems Manager Session Manager** instead (an IAM instance role
  with `AmazonSSMManagedInstanceCore`) — zero inbound ports, no SSH key
  pair to provision or lose, full session logging via CloudTrail. Per
  AWS's own guidance:
  [security group rules](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/security-group-rules.html),
  [Session Manager](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager.html).
- **Elastic IP**: a stable public IP that survives instance stop/start
  ([AWS docs](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/elastic-ip-addresses-eip.html)) —
  point the domain's `A` record at `terraform output public_ip` (registrar-
  agnostic; Route 53 isn't required).
- **Backup**: a daily AWS Data Lifecycle Manager snapshot of the root
  volume (`infra/backup.tf`) — the one thing genuinely missing from the
  original bare-VPS plan. Covers whole-instance disaster recovery,
  including Docker's named volumes (`postgres_data`,
  `traefik-public-certificates`), which live under `/var/lib/docker` on
  that same volume. Postgres-level `pg_dump`-to-S3 backups would be a
  further improvement, not built here.
- **State**: local (`infra/terraform.tfstate`, gitignored) — a single
  instance managed by one person doesn't warrant a remote S3/DynamoDB
  backend; revisit only if this becomes a team-managed setup.

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars   # fill in real domain/acme_email
terraform init
terraform plan     # review before creating anything real/billable
terraform apply
terraform output public_ip   # point the domain's A record at this
```

`infra/bootstrap.sh` runs automatically as EC2 user-data on first boot —
installs Docker + the Compose plugin, creates the `traefik-public`
network. What Terraform does **not** do: place the real `.env` on the
instance or run `docker compose -f docker-compose.prod.yml up -d` — those
stay manual steps (over Session Manager, not SSH), same as the original
plan, since `.env`'s secrets shouldn't be baked into user-data (visible
via the instance metadata service).

**Requires working AWS credentials** (`aws configure` / `~/.aws/credentials`)
with permission to create EC2/IAM/DLM resources — `terraform plan`/`apply`
fail immediately with `InvalidClientTokenId` if the configured access key
isn't valid.

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
