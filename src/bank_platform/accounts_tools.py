"""LangChain tool wrappers around accounts_server.py. This is the only file
that imports LangChain for the Accounts domain — accounts_server.py itself
stays framework-agnostic, unchanged.
"""

from langchain_core.tools import StructuredTool

from bank_platform import accounts_server
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

ACCOUNTS_TOOLS = [
    StructuredTool.from_function(
        func=pii_guard(idempotent(tool_safe(accounts_server.create_account)), _ACCOUNT_FIELDS),
        handle_tool_error=True,
    ),
    StructuredTool.from_function(
        func=pii_guard(tool_safe(accounts_server.get_account), _ACCOUNT_FIELDS), handle_tool_error=True
    ),
    StructuredTool.from_function(
        func=pii_guard(tool_safe(accounts_server.update_account), _ACCOUNT_FIELDS), handle_tool_error=True
    ),
    # delete_account is deliberately NOT exposed here - closing an account
    # is not a customer/agent self-service action, it needs elevated
    # (staff/admin) access that doesn't exist yet (no IAM - see Phase 6).
    # No "apply for closure" path exists yet either (service_agent's
    # request_type allowlist has no closure type) - that's a real gap, not
    # implemented here, flagged for whoever builds the admin/IAM layer.
    # accounts_server.delete_account itself is untouched and still used by
    # test cleanup helpers - only its customer/agent-facing exposure is
    # removed.
]
