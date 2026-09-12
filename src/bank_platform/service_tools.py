"""LangChain tool wrappers around service_server.py. This is the only file
that imports LangChain for the Service domain — service_server.py itself
stays framework-agnostic, unchanged.
"""

from langchain_core.tools import StructuredTool

from bank_platform import service_server
from bank_platform.authz import owner_guard
from bank_platform.tool_utils import idempotent, tool_safe

# No Phase 5 (PII Redaction) wrapping here, deliberately: nothing in this
# domain is unambiguously personal data the way Account.owner_name is -
# account_id/details are an identifier and operational free text, and
# tokenizing them made tool results templated enough to measurably
# increase tool-call hallucination in live testing (PROBLEMS.md #21). See
# accounts_tools.py for the narrow scope that IS applied.

# create already takes account_id directly; get/update/delete only take
# the request's own id, so ownership is checked via a one-row lookup of
# that request's account_id first (service_server.get_service_request_account_id).
_by_account_id = lambda kwargs: kwargs.get("account_id")
_by_request_id = lambda kwargs: service_server.get_service_request_account_id(kwargs.get("id"))

SERVICE_TOOLS = [
    StructuredTool.from_function(
        func=owner_guard(
            idempotent(tool_safe(service_server.create_service_request)), resolve_account_id=_by_account_id
        ),
        handle_tool_error=True,
    ),
    StructuredTool.from_function(
        func=owner_guard(tool_safe(service_server.get_service_request), resolve_account_id=_by_request_id),
        handle_tool_error=True,
    ),
    StructuredTool.from_function(
        func=owner_guard(tool_safe(service_server.update_service_request), resolve_account_id=_by_request_id),
        handle_tool_error=True,
    ),
    StructuredTool.from_function(
        func=owner_guard(tool_safe(service_server.delete_service_request), resolve_account_id=_by_request_id),
        handle_tool_error=True,
    ),
]
