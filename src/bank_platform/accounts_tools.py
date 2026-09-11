"""LangChain tool wrappers around accounts_server.py. This is the only file
that imports LangChain for the Accounts domain — accounts_server.py itself
stays framework-agnostic, unchanged.
"""

from langchain_core.tools import StructuredTool

from bank_platform import accounts_server
from bank_platform.tool_utils import idempotent, tool_safe

ACCOUNTS_TOOLS = [
    StructuredTool.from_function(
        func=idempotent(tool_safe(accounts_server.create_account)), handle_tool_error=True
    ),
    StructuredTool.from_function(func=tool_safe(accounts_server.get_account), handle_tool_error=True),
    StructuredTool.from_function(func=tool_safe(accounts_server.update_account), handle_tool_error=True),
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
