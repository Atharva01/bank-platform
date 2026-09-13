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
