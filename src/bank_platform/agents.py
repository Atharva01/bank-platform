from abc import ABC, abstractmethod
from enum import Enum

from pydantic import BaseModel

from bank_platform.exceptions import (
    InsufficientFundsError,
    InvalidStatusTransitionError,
    NotFoundError,
    ValidationError,
)
from bank_platform.interfaces import default_mcp_client

class AgentType(str, Enum):
    ACCOUNTS = 'accounts'
    TRANSACTION = 'transaction'
    SERVICE = 'service'
    COORDINATOR = 'coordinator'  # used for routing errors that never reached a domain agent

class AgentRequest(BaseModel):
    session_id: str
    user_query: str
    intent: str | None = None # filled by co-ordinator, format "<agent>.<operation>"
    payload: dict | None = None # operation arguments, e.g. {"owner_name": "Jane"}

class AgentResponse(BaseModel):
    agent: AgentType
    success: bool
    message: str
    data: dict | None = None
    error: str | None = None


class Agent(ABC):
    """Base interface every domain agent (Accounts/Transaction/Service) implements."""

    agent_type: AgentType

    def __init__(self, mcp_client=None):
        self.mcp_client = mcp_client or default_mcp_client

    @abstractmethod
    def handle(self, request: AgentRequest) -> AgentResponse: ...


_ALLOWED_OPERATIONS = {
    AgentType.ACCOUNTS: {"create", "read", "update", "delete"},
    AgentType.TRANSACTION: {"create", "read", "update", "delete", "list"},
    AgentType.SERVICE: {"create", "read", "update", "delete"},
}

def _operation(intent: str | None) -> str:
    if not intent or "." not in intent:
        raise ValueError(f"intent must be '<agent>.<operation>', got {intent!r}")
    agent_name, op = intent.split(".", 1)
    allowed = _ALLOWED_OPERATIONS.get(AgentType(agent_name), set())
    if op not in allowed:
        raise ValueError(f"'{op}' is not a valid operation for '{agent_name}'")
    return op


class AccountsAgent(Agent):
    agent_type = AgentType.ACCOUNTS

    def handle(self, request: AgentRequest) -> AgentResponse:
        payload = request.payload or {}
        try:
            op = _operation(request.intent)
        except ValueError as e:
            return AgentResponse(
                agent=self.agent_type, success=False, message=str(e),
                error="invalid_intent",
            )

        try:
            if op == "create":
                data = self.mcp_client.call_tool("create_account", {
                    "owner_name": payload["owner_name"], "balance": payload.get("balance", 0),
                })
            elif op == "read":
                data = self.mcp_client.call_tool("get_account", {"id": payload["id"]})
            elif op == "update":
                data = self.mcp_client.call_tool("update_account", {
                    "id": payload["id"],
                    "owner_name": payload.get("owner_name"), "balance": payload.get("balance"),
                })
            elif op == "delete":
                data = self.mcp_client.call_tool("delete_account", {"id": payload["id"]})
            else:
                return AgentResponse(
                    agent=self.agent_type, success=False, message=f"Unknown operation: {op}",
                    error="unknown_operation",
                )
        except KeyError as e:
            return AgentResponse(
                agent=self.agent_type, success=False, message=f"Missing required field: {e}",
                error="missing_field",
            )
        except NotFoundError as e:
            return AgentResponse(
                agent=self.agent_type, success=False, message=str(e), error="not_found",
            )
        except ValidationError as e:
            return AgentResponse(
                agent=self.agent_type, success=False, message=str(e), error="validation_error",
            )

        return AgentResponse(
            agent=self.agent_type, success=True, message=f"Account {op} succeeded", data=data,
        )


class TransactionAgent(Agent):
    agent_type = AgentType.TRANSACTION

    def handle(self, request: AgentRequest) -> AgentResponse:
        payload = request.payload or {}
        try:
            op = _operation(request.intent)
        except ValueError as e:
            return AgentResponse(
                agent=self.agent_type, success=False, message=str(e),
                error="invalid_intent",
            )

        try:
            if op == "create":
                data = self.mcp_client.call_tool("create_transaction", {
                    "account_id": payload["account_id"], "amount": payload["amount"],
                    "description": payload.get("description"),
                })
            elif op == "read":
                data = self.mcp_client.call_tool("get_transaction", {"id": payload["id"]})
            elif op == "list":
                transactions = self.mcp_client.call_tool("list_transactions", {
                    "account_id": payload["account_id"],
                })
                return AgentResponse(
                    agent=self.agent_type, success=True, message="Transactions listed",
                    data={"transactions": transactions},
                )
            elif op == "update":
                data = self.mcp_client.call_tool("update_transaction", {
                    "id": payload["id"],
                    "amount": payload.get("amount"), "description": payload.get("description"),
                })
            elif op == "delete":
                data = self.mcp_client.call_tool("delete_transaction", {"id": payload["id"]})
            else:
                return AgentResponse(
                    agent=self.agent_type, success=False, message=f"Unknown operation: {op}",
                    error="unknown_operation",
                )
        except KeyError as e:
            return AgentResponse(
                agent=self.agent_type, success=False, message=f"Missing required field: {e}",
                error="missing_field",
            )
        except NotFoundError as e:
            return AgentResponse(
                agent=self.agent_type, success=False, message=str(e), error="not_found",
            )
        except InsufficientFundsError as e:
            return AgentResponse(
                agent=self.agent_type, success=False, message=str(e), error="insufficient_funds",
            )
        except ValidationError as e:
            return AgentResponse(
                agent=self.agent_type, success=False, message=str(e), error="validation_error",
            )

        return AgentResponse(
            agent=self.agent_type, success=True, message=f"Transaction {op} succeeded", data=data,
        )


class ServiceAgent(Agent):
    agent_type = AgentType.SERVICE

    def handle(self, request: AgentRequest) -> AgentResponse:
        payload = request.payload or {}
        try:
            op = _operation(request.intent)
        except ValueError as e:
            return AgentResponse(
                agent=self.agent_type, success=False, message=str(e),
                error="invalid_intent",
            )

        try:
            if op == "create":
                data = self.mcp_client.call_tool("create_service_request", {
                    "account_id": payload["account_id"], "request_type": payload["request_type"],
                    "details": payload.get("details"),
                })
            elif op == "read":
                data = self.mcp_client.call_tool("get_service_request", {"id": payload["id"]})
            elif op == "update":
                data = self.mcp_client.call_tool("update_service_request", {
                    "id": payload["id"],
                    "status": payload.get("status"), "details": payload.get("details"),
                })
            elif op == "delete":
                data = self.mcp_client.call_tool("delete_service_request", {"id": payload["id"]})
            else:
                return AgentResponse(
                    agent=self.agent_type, success=False, message=f"Unknown operation: {op}",
                    error="unknown_operation",
                )
        except KeyError as e:
            return AgentResponse(
                agent=self.agent_type, success=False, message=f"Missing required field: {e}",
                error="missing_field",
            )
        except NotFoundError as e:
            return AgentResponse(
                agent=self.agent_type, success=False, message=str(e), error="not_found",
            )
        except InvalidStatusTransitionError as e:
            return AgentResponse(
                agent=self.agent_type, success=False, message=str(e),
                error="invalid_status_transition",
            )
        except ValidationError as e:
            return AgentResponse(
                agent=self.agent_type, success=False, message=str(e), error="validation_error",
            )

        return AgentResponse(
            agent=self.agent_type, success=True, message=f"Service request {op} succeeded", data=data,
        )
