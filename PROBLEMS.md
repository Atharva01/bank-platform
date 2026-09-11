# Problems Encountered & How They Were Solved

A running log of real issues hit during development — not just what was built,
but what went wrong, why, and the reasoning behind the fix. Kept alongside
`PROGRESS.md` (which tracks phase status) as evidence of the judgment calls
behind the code, not just the code itself.

---

## 1. Uncaught `NameError` in operation-validation dict

**Problem:** A hand-written `_allowed_op_per_agent` dict in `agents.py` used bare
identifiers (`create`, `read`, `update`, `delete`) instead of quoted strings,
and was rebuilt on every call without ever being used by the function. It also
keyed on `"account"` (singular) while the real intent prefix is `"accounts"`
(plural).

**Root cause:** Copy-drafted dict left unquoted; not caught because the
function's actual return value (`intent.split(".", 1)[1]`) never referenced
the dict, so no test exercised it directly at first.

**Solution:** Rebuilt as a module-level `_ALLOWED_OPERATIONS` dict with correct
string keys/values, keyed by `AgentType` enum (not raw strings) to eliminate
the singular/plural mismatch, and wired into `_operation()`'s actual
validation logic instead of sitting inert.

**Why it mattered:** Would have crashed with a raw `500` on literally every
`/chat` request, not just invalid ones — caught before commit by running the
code, not just reading it.

---

## 2. Missing payload fields crashed with a raw HTTP 500

**Problem:** Manual endpoint testing (`accounts.create` with an empty
payload) returned `HTTP 500 Internal Server Error` with no JSON body, instead
of the clean `AgentResponse` error shape every other failure path used.

**Root cause:** `payload["owner_name"]`-style direct dict indexing raises
`KeyError` when a required field is missing, and nothing caught it —
`coordinator.py` and `agents.py` only handled `ValueError` (invalid intent)
and explicit `None` checks (not-found), not missing keys.

**Solution:** Wrapped each agent's `handle()` body in `except KeyError as e`,
returning a `missing_field` error response instead of letting the exception
propagate to FastAPI's default handler.

**Why it mattered:** Found by actually exercising the API over HTTP, not just
unit-testing the happy path — the gap only showed up because real requests
were sent and their status codes checked, not assumed.

---

## 3. Coordinator used a misleading `AgentType` for routing errors

**Problem:** Errors that occurred *before* a request reached any domain agent
(invalid intent format, unknown agent name) were tagged `agent: "accounts"` in
the response — implying the Accounts agent handled them, when it never saw
the request.

**Root cause:** No neutral value existed to represent "the Coordinator itself
rejected this."

**Solution:** Added `AgentType.COORDINATOR` specifically for this case, used
only for pre-routing failures.

**Why it mattered:** Small, but matters for observability later — logs/traces
built on `AgentResponse.agent` need to distinguish "Coordinator rejected it"
from "Accounts agent rejected it" for debugging routing vs. business-logic
failures.

---

## 4. Default git branch mismatch (`master` vs `main`)

**Problem:** `gh repo create --source=. --push` pushed local `master` and set
it as the GitHub default, but the project convention (and local branch after
a manual rename) was `main` — leaving `origin/master` as the actual default
with `main` orphaned until fixed.

**Solution:** Renamed the local branch, pushed `main`, explicitly set it as
the GitHub default via `gh repo edit --default-branch`, then deleted the
stale `origin/master`.

**Why it mattered:** A silent default-branch mismatch is easy to miss until a
PR targets the wrong base — caught immediately because the state was checked
(`git branch -a`, `git status`) rather than assumed correct after one command.

---

## 5. Two Postgres containers competing for port 5432

**Problem:** An unrelated project (`fastapi-postgresql-learning`) already had
a Postgres container bound to host port 5432. Bringing up `bank-platform`'s
own container risked a silent port conflict.

**Solution:** Checked `docker ps -a` before starting anything new, confirmed
the older container was stopped (`Exited`), and explicitly `docker stop`'d it
to guarantee the port was free rather than assuming state from memory.

**Why it mattered:** Two containers with different credentials/DB names
(`appuser/appdb` vs `bank/bank_platform`) silently pointing at the same port
would have caused confusing, hard-to-diagnose connection errors later.

---

## 6. `pytest` couldn't import project modules

**Problem:** `uv run pytest` failed at collection with
`ModuleNotFoundError: No module named 'database'` — even though `database.py`
sits at the project root next to the tests.

**Root cause:** With no `__init__.py` files, pytest's rootless import mode
inserts each test *file's* directory onto `sys.path`, not the project root —
so `tests/conftest.py` couldn't see `database.py` one level up.

**Solution:** Added `[tool.pytest.ini_options] pythonpath = ["."]` to
`pyproject.toml`.

---

## 7. Transaction creation didn't touch account balance (design gap, not a bug)

**Problem:** After the initial CRUD build, `transaction.create` inserted a row
into `transactions` but never updated the linked account's `balance` — the
two tables were functionally unrelated despite the obvious real-world
expectation that a deposit changes what the account is worth.

**Root cause:** The initial build was scoped to prove agent *coordination*
end-to-end (routing, CRUD, error handling), not real banking business rules —
this was a deliberate simplification, caught and flagged during a planning
discussion rather than discovered as a bug report.

**Solution:** Designed and implemented `create_transaction_and_update_balance()`
as a single atomic function (see `PROGRESS.md` Phase 1 step 2) rather than two
separate writes — driven by a follow-on realization (see #8) that two
independently-committed writes can't be made atomic once the operation is
split across an MCP tool-call boundary later.

**Why it mattered:** Caught during design discussion, before implementation —
avoided building an API shape (agent orchestrating two separate crud calls)
that would have needed a breaking redesign once MCP servers are introduced.

---

## 8. Money arithmetic in `float` risks precision drift

**Problem:** Account balances and transaction amounts were being read out of
Postgres `Numeric(12,2)` columns, converted to Python `float` for JSON
responses, and (in the planned balance-linkage logic) would have been added
using float arithmetic — which cannot represent most decimal fractions
exactly (`0.1 + 0.2 != 0.3` in IEEE 754).

**Solution:** Switched balance/amount arithmetic to Python's `Decimal`
end-to-end in the business-logic layer (`create_transaction_and_update_balance`
converts via `Decimal(str(amount))`), keeping `float` only at the JSON
response boundary where exactness no longer matters.

**Why it mattered:** Caught proactively during a tech-stack discussion before
any balance-affecting code was written — the kind of bug that wouldn't fail a
test with small round numbers but would silently accumulate error over many
real transactions.

---

## Template for new entries

```
## N. <short title>

**Problem:** what broke or was missing, and how it was noticed.
**Root cause:** the actual underlying reason, not just the symptom.
**Solution:** what was changed and why that approach specifically.
**Why it mattered:** the judgment call / risk avoided, in plain terms.
```
