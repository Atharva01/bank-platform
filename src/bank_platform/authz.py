"""Ownership enforcement - added to close a real gap found in the Phase 7
deviation review: any caller (chat or REST) could act on any account_id it
named or guessed, since no customer identity existed anywhere. See the
account-schema-redesign-deferred memory's 2026-09-12 update - this adds a
credential + an ownership link only, it does not redesign what
Account.owner_name means.

Two call sites share this one rule: REST routers call require_owner()
directly (they already have an explicit customer_id from
Depends(get_current_customer)); chat tools use the owner_guard() decorator,
which reads customer_id out of the RunnableConfig using the same
injection technique as pii_guard/idempotent (tool_utils.py), so the LLM
never sees or supplies it.

Deliberately raises the ordinary NotFoundError for both "doesn't exist"
and "not yours" - a caller must not be able to distinguish an account it
can't access from one that was never there (standard IDOR mitigation).
"""

from functools import wraps

from langchain_core.runnables import RunnableConfig

from bank_platform import accounts_server
from bank_platform.exceptions import NotFoundError


def require_owner(account_id: str, customer_id: str | None) -> None:
    owner_id = accounts_server.get_account_owner(account_id)
    if owner_id is None or owner_id != customer_id:
        raise NotFoundError(f"Account {account_id} not found")


def owner_guard(func, resolve_account_id):
    """Outermost wrapper around a chat tool (wraps pii_guard/idempotent/
    tool_safe, not the other way around) so access is denied before any
    PII detokenization or business logic runs.

    resolve_account_id(kwargs) -> the account_id to check ownership of,
    given the tool's real incoming kwargs (account_id/id are never
    tokenized - see pii_guard.py's narrowed scope - so these are always
    real values, safe to check directly).
    """
    # Same reasoning as pii_guard's identical check: only forward `config`
    # to the inner function if it actually declares one.
    forwards_config = "config" in getattr(func, "__annotations__", {})

    @wraps(func)
    def wrapper(*args, config: RunnableConfig, **kwargs):
        customer_id = (config or {}).get("configurable", {}).get("customer_id")
        require_owner(resolve_account_id(kwargs), customer_id)
        if forwards_config:
            return func(*args, config=config, **kwargs)
        return func(*args, **kwargs)

    wrapper.__annotations__ = dict(wrapper.__annotations__)
    wrapper.__annotations__["config"] = RunnableConfig
    return wrapper


def inject_customer_id(func):
    """For tools that create a new customer-owned resource (create_account,
    list_accounts) rather than acting on an existing one: forces the real
    customer_id from RunnableConfig into the call, never as an LLM-fillable
    argument. A plain `customer_id` parameter on the wrapped business
    function would otherwise leak into the tool's schema once LangChain's
    inference unwraps through the wrap chain to it (verified directly -
    unlike `config: RunnableConfig`, which LangChain excludes by type
    annotation regardless of nesting, an ordinary-typed parameter is not
    auto-hidden). The caller must construct the StructuredTool with an
    explicit `args_schema` naming only the real user-facing args, since
    schema inference can't be trusted to hide this one on its own.

    Must be the outermost wrapper (wraps pii_guard/idempotent/tool_safe)
    so idempotent's dedup key and pii_guard's tokenization both see the
    real customer_id already applied.
    """
    # Same reasoning as owner_guard/pii_guard: only forward `config` to the
    # inner function if it actually declares one - a tool_safe-only chain
    # (e.g. list_accounts, with no pii_guard/idempotent involved) doesn't,
    # and would otherwise swallow an unexpected config kwarg into **kwargs
    # and crash the real server function.
    forwards_config = "config" in getattr(func, "__annotations__", {})

    @wraps(func)
    def wrapper(*args, config: RunnableConfig, **kwargs):
        customer_id = (config or {}).get("configurable", {}).get("customer_id")
        if forwards_config:
            return func(*args, config=config, customer_id=customer_id, **kwargs)
        return func(*args, customer_id=customer_id, **kwargs)

    wrapper.__annotations__ = dict(wrapper.__annotations__)
    wrapper.__annotations__["config"] = RunnableConfig
    return wrapper
