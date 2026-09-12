"""The LangGraph supervisor + 3 specialist sub-agents. This is the
orchestration layer that replaced coordinator.py's rule-based routing and
agents.py's fixed intent-parsing — the LLM now decides which sub-agent to
delegate to and which tools to call, based on free-text user input.
"""

from datetime import datetime, timedelta, timezone

from openai import APITimeoutError, BadRequestError

from langchain.agents import create_agent
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph_supervisor import create_supervisor

from bank_platform import pii_guard, session_store
from bank_platform.accounts_tools import ACCOUNTS_TOOLS
from bank_platform.database import DATABASE_URL
from bank_platform.exceptions import SessionOwnershipError
from bank_platform.llm import llm
from bank_platform.service_tools import SERVICE_TOOLS
from bank_platform.tool_utils import _completed_calls
from bank_platform.transactions_tools import TRANSACTIONS_TOOLS

# Idle-session timeout (Phase 4 - Session Store). Deliberately short: this
# is scoped as focused, single-sitting banking interactions, not a
# long-lived chat session - decided with the user, not an arbitrary default.
SESSION_IDLE_TIMEOUT = timedelta(minutes=10)

# Named module-level constants (not inline literals) so their content can
# be unit-tested directly - e.g. "does the supervisor prompt still mention
# every agent and the anti-re-delegation rule" - without invoking the LLM.
# This is a structural regression guard only; it can't verify the LLM
# actually follows these instructions, which needs a real evaluation
# harness against the live model (see PROGRESS.md Phase 9 - not done yet).


# Shared across all three sub-agent prompts: the customer never sees the
# multi-agent architecture, and the reply must not describe one - no
# "as reported by the accounts agent/team", no "delegating to...", no
# naming a tool. Write the final answer exactly as a bank would say it
# directly to the customer.
_NO_INTERNALS_RULE = (
    "Write your final answer directly to the customer, in first person, "
    "as the bank's own assistant would - never mention agents, teams, "
    "tools, or that this request was routed/delegated internally (e.g. "
    "do NOT say 'as reported by the accounts team/agent' or similar)."
)

ACCOUNTS_AGENT_PROMPT = (
    "You handle bank account operations: opening a new account, "
    "viewing an account's details/balance, and updating its owner "
    "name or balance. You cannot close an account - that requires "
    "staff/elevated access. If asked to close an account, say so "
    "plainly and do not attempt it with any other tool. The caller is "
    "always an authenticated customer - if they ask about 'my "
    "account'/'my balance' without stating an account id, call "
    "list_accounts first to find their own account(s) rather than "
    "asking them for an id they may not have memorized. Use your "
    "tools to fulfil the user's request, then report back what "
    "happened in plain language. " + _NO_INTERNALS_RULE
)

TRANSACTION_AGENT_PROMPT = (
    "You handle transactions: deposits, withdrawals, viewing statement "
    "history, and correcting or reversing past transactions. The caller "
    "is always an authenticated customer - if they say 'my account' "
    "without stating an account id, call list_accounts first to find "
    "their own account(s) rather than asking them for an id they may not "
    "have memorized. Use your "
    "tools to fulfil the user's request, then report back what "
    "happened in plain language. If your own prior message in this "
    "conversation already reports that this exact deposit/withdrawal "
    "was completed, do NOT call the tool again — just restate that "
    "result. Each transaction tool call moves real money; never call "
    "one more than once for the same user request. " + _NO_INTERNALS_RULE
)

SERVICE_AGENT_PROMPT = (
    "You handle service requests: change of address, cheque book "
    "requests, and KYC updates. The caller is always an authenticated "
    "customer - if they don't state an account id, call list_accounts "
    "first to find their own account(s) rather than asking them for an "
    "id they may not have memorized. Use your tools to fulfil the "
    "user's request, then report back what happened in plain language. "
    + _NO_INTERNALS_RULE
)

SUPERVISOR_PROMPT = (
    "You are the routing supervisor for a banking assistant. You have "
    "no tools of your own and no banking knowledge of your own — your "
    "only job is to route each request to exactly one specialist "
    "agent below, then relay that agent's final answer to the user "
    "VERBATIM - do not add any framing like 'as reported by the X "
    "team/agent', do not mention that the request was routed or "
    "delegated internally, and do not summarize or rephrase it. The "
    "customer must never see that a multi-agent system exists. "
    "Never answer a banking question yourself from your own "
    "knowledge; only a specialist agent's tool result is a valid "
    "basis for a factual answer.\n\n"
    "AVAILABLE AGENTS — job and limits:\n"
    "- accounts_agent: opening a new account, viewing an account's "
    "details/balance, updating an account's owner name or balance. "
    "Does NOT close accounts (requires staff/elevated access, not "
    "available to this assistant at all - tell the user to contact "
    "the bank directly for that), and does NOT handle "
    "deposits/withdrawals (transaction_agent's job) or "
    "address/cheque-book/KYC requests (service_agent's job).\n"
    "- transaction_agent: money movement ONLY — deposits, "
    "withdrawals, viewing transaction/statement history, correcting "
    "or reversing a past transaction. Does NOT open accounts, close "
    "accounts, or handle service requests.\n"
    "- service_agent: non-financial service tickets ONLY — change of "
    "address, cheque book requests, KYC updates, checking a service "
    "request's status. Does NOT move money or manage account "
    "lifecycle.\n\n"
    "ROUTING RULES:\n"
    "1. Route to exactly one agent per request, exactly once. Once "
    "an agent reports a request complete, relay that result to the "
    "user — do NOT delegate again for the same request, even to "
    "double-check or confirm. Re-delegating a completed financial "
    "transaction risks applying it twice.\n"
    "2. If a request doesn't clearly fall within one agent's stated "
    "job above, or isn't a banking request at all, do not guess and "
    "do not delegate — reply directly and ask the user to clarify "
    "which of the three areas above they mean."
)

accounts_agent = create_agent(model=llm, tools=ACCOUNTS_TOOLS, system_prompt=ACCOUNTS_AGENT_PROMPT, name="accounts_agent")
transaction_agent = create_agent(
    model=llm, tools=TRANSACTIONS_TOOLS, system_prompt=TRANSACTION_AGENT_PROMPT, name="transaction_agent"
)
service_agent = create_agent(model=llm, tools=SERVICE_TOOLS, system_prompt=SERVICE_AGENT_PROMPT, name="service_agent")

# PostgresSaver needs a plain libpq-style URL, not SQLAlchemy's
# dialect-qualified one (postgresql+psycopg://) - derived from the same
# DATABASE_URL every other module uses, not a second hardcoded constant.
# connect_timeout matches database.py's - without it, a dead/unreachable
# Postgres can hang a request indefinitely instead of failing fast.
_PG_CONN_STRING = DATABASE_URL.replace("postgresql+psycopg://", "postgresql://") + "?connect_timeout=10"
_checkpointer_cm = PostgresSaver.from_conn_string(_PG_CONN_STRING)
_checkpointer = _checkpointer_cm.__enter__()  # long-lived, module-level - mirrors every other module's one-time setup
_checkpointer.setup()  # one-time: creates the checkpointer's own tables, separate from models.py

supervisor = create_supervisor(
    agents=[accounts_agent, transaction_agent, service_agent],
    model=llm,
    prompt=SUPERVISOR_PROMPT,
).compile(checkpointer=_checkpointer)


def _expire_session(session_id: str) -> None:
    """Cleans up everything tied to one session's lifecycle together - the
    checkpoint thread, the idempotency dedup dict, the PII token map
    (Phase 5), and the sessions row - so none of them drift out of sync.
    Shared by both the per-request lazy check (_expire_if_idle) and the
    periodic sweep (sweep_expired_sessions).
    """
    _checkpointer.delete_thread(session_id)
    _completed_calls.pop(session_id, None)
    pii_guard.forget_thread(session_id)
    session_store.delete(session_id)


def _expire_if_idle(session_id: str) -> None:
    """Lazy, per-session expiry - runs once per /chat request, so it only
    ever catches a session actually still in use. A session that's
    abandoned outright (never messaged again) wouldn't be caught by this
    alone - sweep_expired_sessions() (run periodically, see main.py) covers
    that case.
    """
    last_activity = session_store.get_last_activity(session_id)
    if last_activity is None:
        return  # new session, nothing to expire
    if datetime.now(timezone.utc) - last_activity > SESSION_IDLE_TIMEOUT:
        _expire_session(session_id)


def sweep_expired_sessions() -> int:
    """Proactively cleans up every session that's gone idle past the
    timeout, not just the one in the current request - closes the residual
    gap _expire_if_idle leaves (an abandoned session that's never messaged
    again previously lingered in Postgres indefinitely). Cheap: one query
    plus per-session cleanup, run on a timer (main.py's lifespan task), no
    new dependency needed. Returns the number of sessions cleaned up.
    """
    cutoff = datetime.now(timezone.utc) - SESSION_IDLE_TIMEOUT
    expired_ids = session_store.list_expired_session_ids(cutoff)
    for session_id in expired_ids:
        _expire_session(session_id)
    return len(expired_ids)


def _extract_reply(messages) -> str:
    """The last AI message that's a genuine final answer - has content and
    isn't itself mid-handoff (a message with pending tool_calls). Not just
    "the last message": the supervisor's own closing remark after a
    sub-agent hands back is sometimes an empty/generic filler rather than
    the actual result (observed run-to-run variance) - the sub-agent's own
    final answer is the reliable one to surface.
    """
    for message in reversed(messages):
        content = getattr(message, "content", None)
        tool_calls = getattr(message, "tool_calls", None)
        if type(message).__name__ == "AIMessage" and content and not tool_calls:
            return content
    return "I couldn't process that request."


def _bind_or_verify_customer(session_id: str, customer_id: str) -> None:
    """session_id is still a client-chosen opaque string with no identity
    of its own - without this, two different authenticated customers could
    collide on the same session_id and share one thread's conversation
    history/state. Binds the first customer to use a thread; rejects any
    other customer trying to reuse it later. Uses session_store.py's
    shared-state (Phase 4, previously unconsumed) rather than a new store."""
    bound_customer_id = session_store.store.get(session_id).get("customer_id")
    if bound_customer_id is None:
        session_store.store.update(session_id, {"customer_id": customer_id})
    elif bound_customer_id != customer_id:
        raise SessionOwnershipError(f"session_id {session_id!r} is already in use by a different customer")


def _invoke(message: str, session_id: str, customer_id: str) -> dict:
    """Runs the graph, resuming from its last checkpoint on a retryable LLM
    failure (a malformed tool-call response the provider's own API rejects,
    e.g. PROBLEMS.md #12/#19, or a request that timed out - see llm.py's
    `timeout`) instead of restarting the whole invocation. A restart would
    silently re-run any tool call that already succeeded before the
    failure (e.g. double-applying a deposit) - resuming via the same
    thread_id continues past the last completed step instead, since
    LangGraph checkpoints after every superstep and a completed tool call
    is never re-entered on resume.

    thread_id = session_id directly (Phase 4) - the caller's session now
    genuinely persists conversation history across separate /chat calls,
    instead of a fresh UUID being generated (and immortalized) on every
    single request.

    The incoming message is sanitized (Phase 5 - PII Redaction) before it
    enters the graph: any real value the system already knows about from
    earlier in this thread (e.g. the user pasting back an account ID it
    gave them) is replaced with its existing token, so it doesn't reach
    the LLM in raw form. This is a known-value substitution only, not
    general PII detection - see pii_guard.py's module docstring.
    """
    config = {"configurable": {"thread_id": session_id, "customer_id": customer_id}}
    sanitized_message = pii_guard.sanitize_incoming(message, session_id)
    payload = {"messages": [{"role": "user", "content": sanitized_message}]}
    attempts = 3
    for attempt in range(attempts):
        try:
            return supervisor.invoke(payload, config=config)
        except (BadRequestError, APITimeoutError):
            if attempt == attempts - 1:
                raise
            payload = None  # resume from checkpoint, don't replay from scratch


def run(message: str, session_id: str, customer_id: str) -> str:
    """Runs one user message through the supervisor graph, within the given
    session's conversation, and returns the final natural-language reply.

    _extract_reply() only searches messages added by THIS invocation, not
    the full persisted history (Phase 4 made threads multi-use across
    separate run() calls, unlike before when a thread was always
    single-use and "whole history" and "this turn" were the same set) -
    otherwise, if this turn somehow produced no fresh final AIMessage, the
    heuristic would silently fall back to an EARLIER turn's stored answer
    instead of surfacing that something went wrong.
    """
    _expire_if_idle(session_id)
    _bind_or_verify_customer(session_id, customer_id)
    session_store.touch(session_id)
    config = {"configurable": {"thread_id": session_id}}
    prior_state = supervisor.get_state(config)
    prior_count = len(prior_state.values.get("messages", [])) if prior_state.values else 0
    result = _invoke(message, session_id, customer_id)
    reply = _extract_reply(result["messages"][prior_count:])
    # Phase 5 (PII Redaction): the LLM only ever reasoned over tokens
    # (pii_guard.pii_guard wraps every tool), so its reply text may
    # contain them too (e.g. "your balance on [ACCOUNT_ID_1] is
    # [BALANCE_1]") - swap back to real values for the actual caller.
    return pii_guard.detokenize(reply, session_id)
