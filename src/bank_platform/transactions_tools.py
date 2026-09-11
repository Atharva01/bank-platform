"""LangChain tool wrappers around transactions_server.py. This is the only
file that imports LangChain for the Transactions domain —
transactions_server.py itself stays framework-agnostic, unchanged.
"""

from langchain_core.tools import StructuredTool

from bank_platform import transactions_server
from bank_platform.tool_utils import idempotent, tool_safe

TRANSACTIONS_TOOLS = [
    StructuredTool.from_function(
        func=idempotent(tool_safe(transactions_server.create_transaction)), handle_tool_error=True
    ),
    StructuredTool.from_function(func=tool_safe(transactions_server.get_transaction), handle_tool_error=True),
    StructuredTool.from_function(func=tool_safe(transactions_server.list_transactions), handle_tool_error=True),
    StructuredTool.from_function(func=tool_safe(transactions_server.update_transaction), handle_tool_error=True),
    StructuredTool.from_function(func=tool_safe(transactions_server.delete_transaction), handle_tool_error=True),
]
