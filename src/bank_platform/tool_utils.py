"""Shared helper for wrapping MCP server functions as LangChain tools.

LangChain's handle_tool_error only catches its own ToolException, not
arbitrary exceptions — so our domain exceptions (exceptions.py) need
translating before a server function can be wrapped safely.
"""

from functools import wraps

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
