"""LangChain tool wrappers around transactions_server.py. This is the only
file that imports LangChain for the Transactions domain —
transactions_server.py itself stays framework-agnostic, unchanged.
"""

from langchain_core.tools import StructuredTool

from bank_platform import transactions_server
from bank_platform.authz import owner_guard
from bank_platform.tool_utils import idempotent, tool_safe

# No Phase 5 (PII Redaction) wrapping here, deliberately: nothing in this
# domain is unambiguously personal data the way Account.owner_name is -
# account_id/amount/description are identifiers, financial data, or
# operational free text, and tokenizing them made tool results
# templated enough to measurably increase tool-call hallucination in live
# testing (PROBLEMS.md #21). See accounts_tools.py for the narrow scope
# that IS applied.

# create/list already take account_id directly; get/update/delete only
# take the transaction's own id, so ownership is checked via a one-row
# lookup of that transaction's account_id first (transactions_server.
# get_transaction_account_id) - same NotFoundError either way if the
# transaction doesn't exist or isn't the caller's.
_by_account_id = lambda kwargs: kwargs.get("account_id")
_by_transaction_id = lambda kwargs: transactions_server.get_transaction_account_id(kwargs.get("id"))

TRANSACTIONS_TOOLS = [
    StructuredTool.from_function(
        func=owner_guard(
            idempotent(tool_safe(transactions_server.create_transaction)), resolve_account_id=_by_account_id
        ),
        handle_tool_error=True,
    ),
    StructuredTool.from_function(
        func=owner_guard(tool_safe(transactions_server.get_transaction), resolve_account_id=_by_transaction_id),
        handle_tool_error=True,
    ),
    StructuredTool.from_function(
        func=owner_guard(tool_safe(transactions_server.list_transactions), resolve_account_id=_by_account_id),
        handle_tool_error=True,
    ),
    StructuredTool.from_function(
        func=owner_guard(tool_safe(transactions_server.update_transaction), resolve_account_id=_by_transaction_id),
        handle_tool_error=True,
    ),
    StructuredTool.from_function(
        func=owner_guard(tool_safe(transactions_server.delete_transaction), resolve_account_id=_by_transaction_id),
        handle_tool_error=True,
    ),
]
