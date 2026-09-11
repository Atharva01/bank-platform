"""LangChain tool wrappers around accounts_server.py. This is the only file
that imports LangChain for the Accounts domain — accounts_server.py itself
stays framework-agnostic, unchanged.
"""

from langchain_core.tools import StructuredTool

from bank_platform import accounts_server
from bank_platform.tool_utils import tool_safe

ACCOUNTS_TOOLS = [
    StructuredTool.from_function(func=tool_safe(accounts_server.create_account), handle_tool_error=True),
    StructuredTool.from_function(func=tool_safe(accounts_server.get_account), handle_tool_error=True),
    StructuredTool.from_function(func=tool_safe(accounts_server.update_account), handle_tool_error=True),
    StructuredTool.from_function(func=tool_safe(accounts_server.delete_account), handle_tool_error=True),
]
