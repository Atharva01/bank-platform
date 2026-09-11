"""LangChain tool wrappers around service_server.py. This is the only file
that imports LangChain for the Service domain — service_server.py itself
stays framework-agnostic, unchanged.
"""

from langchain_core.tools import StructuredTool

from bank_platform import service_server
from bank_platform.tool_utils import idempotent, tool_safe

SERVICE_TOOLS = [
    StructuredTool.from_function(
        func=idempotent(tool_safe(service_server.create_service_request)), handle_tool_error=True
    ),
    StructuredTool.from_function(func=tool_safe(service_server.get_service_request), handle_tool_error=True),
    StructuredTool.from_function(func=tool_safe(service_server.update_service_request), handle_tool_error=True),
    StructuredTool.from_function(func=tool_safe(service_server.delete_service_request), handle_tool_error=True),
]
