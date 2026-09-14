"""LangChain tool wrappers around accounts_server.py. This is the only file
that imports LangChain for the Accounts domain — accounts_server.py itself
stays framework-agnostic, unchanged.
"""

from pydantic import BaseModel

from langchain_core.tools import StructuredTool

from bank_platform import accounts_server
from bank_platform.authz import inject_customer_id, owner_guard
from bank_platform.pii_guard import pii_guard
from bank_platform.tool_utils import idempotent, tool_safe

# Phase 5 (PII Redaction) - fields tokenized before an account reaches the
# LLM's context; see pii_guard.py. Deliberately narrow: only owner_name -
# the one field that's unambiguously personal data and rarely needs to be
# echoed back as a tool argument. id/balance were tokenized too at first,
# but that made almost every field in every tool result a token, which
# measurably increased tool-call hallucination in live testing (the model
# relaying/reasoning over a context this templated - PROBLEMS.md #21).
# Not tokenizing an ID is a reasonable tradeoff: it's an opaque UUID this
# app already treats as non-secret (used in URLs, etc.), not personal
# data in the traditional sense.
_ACCOUNT_FIELDS = {"owner_name": "OWNER_NAME"}


class _CreateAccountArgs(BaseModel):
    """Explicit args_schema for create_account - see authz.inject_customer_id's
    docstring for why this can't be left to schema inference: customer_id
    must never be an LLM-fillable argument."""

    owner_name: str
    balance: float = 0


class _ListAccountsArgs(BaseModel):
    """Empty on purpose - list_accounts takes no real arguments, only the
    config-injected customer_id."""


class _UpdateAccountArgs(BaseModel):
    """Explicit args_schema for update_account - deliberately excludes
    `balance` even though accounts_server.update_account still accepts it
    as a parameter. Balance may only ever change via a Transaction
    (transaction_agent's deposit/withdraw, atomically ledger-linked) -
    letting a customer set it directly here bypassed that entirely (found
    in Phase 10's security review, see PROBLEMS.md)."""

    id: str
    owner_name: str


# Shared across all three sub-agents (accounts/transaction/service), not
# just this domain's own tool list - found live that transaction_agent and
# service_agent had no way to resolve "my account" and asked the customer
# for an account id they didn't already know, even though they're
# authenticated. Every sub-agent needs the same way out of that.
LIST_ACCOUNTS_TOOL = StructuredTool.from_function(
    func=inject_customer_id(tool_safe(accounts_server.list_accounts_for_customer)),
    args_schema=_ListAccountsArgs,
    handle_tool_error=True,
    name="list_accounts",
    description="List every account the authenticated customer owns - use this before asking the "
    "customer for an account id, e.g. to answer 'what's my balance', 'what accounts do I have', or "
    "to find which account to act on when the customer says 'my account' without an id.",
)

ACCOUNTS_TOOLS = [
    StructuredTool.from_function(
        func=inject_customer_id(
            pii_guard(idempotent(tool_safe(accounts_server.create_account)), _ACCOUNT_FIELDS)
        ),
        args_schema=_CreateAccountArgs,
        handle_tool_error=True,
    ),
    StructuredTool.from_function(
        func=owner_guard(
            pii_guard(tool_safe(accounts_server.get_account), _ACCOUNT_FIELDS),
            resolve_account_id=lambda kwargs: kwargs.get("id"),
        ),
        handle_tool_error=True,
    ),
    StructuredTool.from_function(
        func=owner_guard(
            pii_guard(tool_safe(accounts_server.update_account), _ACCOUNT_FIELDS),
            resolve_account_id=lambda kwargs: kwargs.get("id"),
        ),
        args_schema=_UpdateAccountArgs,
        handle_tool_error=True,
    ),
    LIST_ACCOUNTS_TOOL,
    # delete_account is deliberately NOT exposed here - closing an account
    # is not a customer/agent self-service action, it needs elevated
    # (staff/admin) access (see Phase 6). No "apply for closure" path
    # exists yet either (service_agent's request_type allowlist has no
    # closure type) - that's a real gap, not implemented here, flagged for
    # whoever builds the admin/IAM layer. accounts_server.delete_account
    # itself is untouched and still used by test cleanup helpers - only
    # its customer/agent-facing exposure is removed.
]
