"""Shared helpers for wrapping MCP server functions as LangChain tools.

LangChain's handle_tool_error only catches its own ToolException, not
arbitrary exceptions — so our domain exceptions (exceptions.py) need
translating before a server function can be wrapped safely.
"""

from functools import wraps

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import ToolException

from bank_platform.exceptions import (
    InsufficientFundsError,
    InvalidStatusTransitionError,
    NotFoundError,
    ValidationError,
)

_DOMAIN_EXCEPTIONS = (
    NotFoundError,
    ValidationError,
    InsufficientFundsError,
    InvalidStatusTransitionError,
)


def tool_safe(func):
    """Wraps a server function so its domain exceptions become ToolException,
    which handle_tool_error=True then turns into a message the LLM sees and
    can react to, instead of crashing the agent graph. Preserves __name__/
    __doc__/signature via functools.wraps, so StructuredTool.from_function's
    schema inference still works on the wrapped function.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except _DOMAIN_EXCEPTIONS as e:
            raise ToolException(str(e)) from e

    return wrapper


_completed_calls: dict[str, set[tuple]] = {}


def idempotent(func):
    """Refuses to re-run a mutating "create" tool call with identical
    arguments within the same conversation thread — a deterministic
    backstop, not a prompt-level suggestion. Observed in practice: the
    LangGraph supervisor occasionally re-delegates an already-completed
    request to the same sub-agent a second time (see PROBLEMS.md #13),
    and a strengthened prompt only reduces that, it can't guarantee it
    against every model response. This makes a duplicate create_transaction
    (etc.) call a no-op instead of a second real deposit/withdrawal/row,
    regardless of why the LLM issued it twice.

    Scoped to create_* only: update/delete calls in this codebase are
    already naturally idempotent (delete of an already-deleted row just
    raises NotFoundError; update_transaction's balance delta is computed
    against the row's current value, so repeating an identical update is a
    no-op) — only "insert a new row" operations are actually unsafe to
    repeat.

    Requires a RunnableConfig with configurable.thread_id, auto-injected by
    LangChain's tool-calling machinery (detected via the `config:
    RunnableConfig` annotation below) — never supplied by the LLM itself.
    Dedup state is process-local and never evicted, same lifetime tradeoff
    as graph.py's in-memory checkpointer (fine for a single-process
    prototype, would need real TTL/persistence before production).
    """

    @wraps(func)
    def wrapper(*args, config: RunnableConfig, **kwargs):
        thread_id = (config or {}).get("configurable", {}).get("thread_id", "")
        call_key = (func.__name__, args, tuple(sorted(kwargs.items())))
        seen = _completed_calls.setdefault(thread_id, set())
        if call_key in seen:
            raise ToolException(
                f"This exact {func.__name__} call already completed earlier "
                "in this conversation and was not repeated. Report the "
                "original result to the user - do not call this tool again "
                "for the same request."
            )
        result = func(*args, **kwargs)
        seen.add(call_key)
        return result

    # @wraps assigns func's own __annotations__ dict onto wrapper BY
    # REFERENCE (not a copy) — mutating it in place would silently add
    # "config" to every function up the wrap chain, including the original
    # server function. Copy first, then add the hint LangChain's
    # RunnableConfig-injection lookup needs (it reads wrapper.__annotations__
    # directly, not the unwrapped original's).
    wrapper.__annotations__ = dict(wrapper.__annotations__)
    wrapper.__annotations__["config"] = RunnableConfig
    return wrapper
