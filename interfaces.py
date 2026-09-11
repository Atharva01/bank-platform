from abc import ABC, abstractmethod

from pydantic import BaseModel


class MCPToolResult(BaseModel):
    tool: str
    result: dict


class MCPClient(ABC):
    """Stub interface for an agent's MCP server connection. Real implementations land in Phase 2."""

    @abstractmethod
    def call_tool(self, tool: str, params: dict) -> MCPToolResult: ...


class SessionStore(ABC):
    """Stub interface for conversation history and inter-agent shared state. Real implementation lands in Phase 4."""

    @abstractmethod
    def get(self, session_id: str) -> dict: ...

    @abstractmethod
    def update(self, session_id: str, data: dict) -> None: ...
