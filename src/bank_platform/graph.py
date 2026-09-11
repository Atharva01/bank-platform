"""The LangGraph supervisor + 3 specialist sub-agents. This is the
orchestration layer that replaced coordinator.py's rule-based routing and
agents.py's fixed intent-parsing — the LLM now decides which sub-agent to
delegate to and which tools to call, based on free-text user input.
"""

import uuid

from openai import BadRequestError

from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver
from langgraph_supervisor import create_supervisor

from bank_platform.accounts_tools import ACCOUNTS_TOOLS
from bank_platform.llm import llm
from bank_platform.service_tools import SERVICE_TOOLS
from bank_platform.transactions_tools import TRANSACTIONS_TOOLS

accounts_agent = create_agent(
    model=llm,
    tools=ACCOUNTS_TOOLS,
    system_prompt=(
        "You handle bank account operations: opening, viewing, updating, "
        "and closing accounts. Use your tools to fulfil the user's request, "
        "then report back what happened in plain language."
    ),
    name="accounts_agent",
)

transaction_agent = create_agent(
    model=llm,
    tools=TRANSACTIONS_TOOLS,
    system_prompt=(
        "You handle transactions: deposits, withdrawals, viewing statement "
        "history, and correcting or reversing past transactions. Use your "
        "tools to fulfil the user's request, then report back what "
        "happened in plain language. If your own prior message in this "
        "conversation already reports that this exact deposit/withdrawal "
        "was completed, do NOT call the tool again — just restate that "
        "result. Each transaction tool call moves real money; never call "
        "one more than once for the same user request."
    ),
    name="transaction_agent",
)

service_agent = create_agent(
    model=llm,
    tools=SERVICE_TOOLS,
    system_prompt=(
        "You handle service requests: change of address, cheque book "
        "requests, and KYC updates. Use your tools to fulfil the user's "
        "request, then report back what happened in plain language."
    ),
    name="service_agent",
)

_checkpointer = InMemorySaver()

supervisor = create_supervisor(
    agents=[accounts_agent, transaction_agent, service_agent],
    model=llm,
    prompt=(
        "You are a banking assistant supervisor. Route the user's request "
        "to exactly one of: accounts_agent (open/view/update/close "
        "accounts), transaction_agent (deposits, withdrawals, statements, "
        "correcting transactions), or service_agent (change of address, "
        "cheque book requests, KYC updates). Do not answer "
        "account/transaction/service questions yourself — always delegate. "
        "Delegate each request to exactly one agent ONCE. Once an agent "
        "reports back that it completed the task, relay that result to the "
        "user — do NOT delegate to any agent again for the same request, "
        "even to double-check or confirm. Re-delegating a completed "
        "financial transaction risks applying it twice."
    ),
).compile(checkpointer=_checkpointer)


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


def _invoke(message: str) -> dict:
    """Runs the graph, resuming from its last checkpoint on gpt-oss-20b's
    occasional tool-call parse failure (see llm.py) instead of restarting
    the whole invocation. A restart would silently re-run any tool call
    that already succeeded before the failure (e.g. double-applying a
    deposit) - resuming via the same thread_id continues past the last
    completed step instead, since LangGraph checkpoints after every
    superstep and a completed tool call is never re-entered on resume.
    """
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    payload = {"messages": [{"role": "user", "content": message}]}
    attempts = 3
    for attempt in range(attempts):
        try:
            return supervisor.invoke(payload, config=config)
        except BadRequestError:
            if attempt == attempts - 1:
                raise
            payload = None  # resume from checkpoint, don't replay from scratch


def run(message: str) -> str:
    """Runs one user message through the supervisor graph and returns the
    final natural-language reply."""
    result = _invoke(message)
    return _extract_reply(result["messages"])
