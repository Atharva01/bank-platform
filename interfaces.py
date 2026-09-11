from abc import ABC, abstractmethod
from typing import Any


class MCPClient(ABC):
    """An agent's connection to the MCP tool layer. call_tool returns the
    tool's result (a dict, or a list of dicts for a listing tool) or raises
    a domain exception from exceptions.py (NotFoundError, ValidationError,
    InsufficientFundsError, InvalidStatusTransitionError) on failure.
    """

    @abstractmethod
    def call_tool(self, tool: str, params: dict) -> Any: ...


class InProcessMCPClient(MCPClient):
    """In-process implementation: dispatches to the three server modules by
    tool name (no subprocess, no real MCP transport — see PROGRESS.md for
    why). Tool names are globally unique across all three servers, so no
    separate domain argument is needed.
    """

    def __init__(self):
        import accounts_server
        import service_server
        import transactions_server

        self._tools = {
            "create_account": accounts_server.create_account,
            "get_account": accounts_server.get_account,
            "update_account": accounts_server.update_account,
            "delete_account": accounts_server.delete_account,
            "create_transaction": transactions_server.create_transaction,
            "get_transaction": transactions_server.get_transaction,
            "list_transactions": transactions_server.list_transactions,
            "update_transaction": transactions_server.update_transaction,
            "delete_transaction": transactions_server.delete_transaction,
            "create_service_request": service_server.create_service_request,
            "get_service_request": service_server.get_service_request,
            "update_service_request": service_server.update_service_request,
            "delete_service_request": service_server.delete_service_request,
        }

    def call_tool(self, tool: str, params: dict) -> Any:
        func = self._tools[tool]
        return func(**params)


default_mcp_client = InProcessMCPClient()


class SessionStore(ABC):
    """Stub interface for conversation history and inter-agent shared state. Real implementation lands in Phase 4."""

    @abstractmethod
    def get(self, session_id: str) -> dict: ...

    @abstractmethod
    def update(self, session_id: str, data: dict) -> None: ...
