from abc import ABC, abstractmethod
from enum import Enum

from pydantic import BaseModel

from database import SessionLocal

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
        import crud_accounts

        session = SessionLocal()
        payload = request.payload or {}
        try:
            try:
                op = _operation(request.intent)
            except ValueError as e:
                return AgentResponse(
                    agent=self.agent_type, success=False, message=str(e),
                    error="invalid_intent",
                )

            if op == "create":
                account = crud_accounts.create_account(
                    session, payload["owner_name"], payload.get("balance", 0)
                )
            elif op == "read":
                account = crud_accounts.get_account(session, payload["id"])
                if account is None:
                    return AgentResponse(
                        agent=self.agent_type, success=False, message="Account not found",
                        error="not_found",
                    )
            elif op == "update":
                account = crud_accounts.update_account(
                    session, payload["id"],
                    owner_name=payload.get("owner_name"), balance=payload.get("balance"),
                )
                if account is None:
                    return AgentResponse(
                        agent=self.agent_type, success=False, message="Account not found",
                        error="not_found",
                    )
            elif op == "delete":
                account = crud_accounts.delete_account(session, payload["id"])
                if account is None:
                    return AgentResponse(
                        agent=self.agent_type, success=False, message="Account not found",
                        error="not_found",
                    )
            else:
                return AgentResponse(
                    agent=self.agent_type, success=False, message=f"Unknown operation: {op}",
                    error="unknown_operation",
                )

            session.commit()
            return AgentResponse(
                agent=self.agent_type, success=True, message=f"Account {op} succeeded",
                data={"id": account.id, "owner_name": account.owner_name, "balance": float(account.balance)},
            )
        except KeyError as e:
            return AgentResponse(
                agent=self.agent_type, success=False, message=f"Missing required field: {e}",
                error="missing_field",
            )
        finally:
            session.close()


class TransactionAgent(Agent):
    agent_type = AgentType.TRANSACTION

    def handle(self, request: AgentRequest) -> AgentResponse:
        import crud_transactions

        session = SessionLocal()
        payload = request.payload or {}
        try:
            try:
                op = _operation(request.intent)
            except ValueError as e:
                return AgentResponse(
                    agent=self.agent_type, success=False, message=str(e),
                    error="invalid_intent",
                )

            if op == "create":
                txn = crud_transactions.create_transaction(
                    session, payload["account_id"], payload["amount"], payload.get("description")
                )
            elif op == "read":
                txn = crud_transactions.get_transaction(session, payload["id"])
                if txn is None:
                    return AgentResponse(
                        agent=self.agent_type, success=False, message="Transaction not found",
                        error="not_found",
                    )
            elif op == "list":
                txns = crud_transactions.get_transactions_for_account(session, payload["account_id"])
                return AgentResponse(
                    agent=self.agent_type, success=True, message="Transactions listed",
                    data={"transactions": [
                        {"id": t.id, "account_id": t.account_id, "amount": float(t.amount), "description": t.description}
                        for t in txns
                    ]},
                )
            elif op == "update":
                txn = crud_transactions.update_transaction(
                    session, payload["id"],
                    amount=payload.get("amount"), description=payload.get("description"),
                )
                if txn is None:
                    return AgentResponse(
                        agent=self.agent_type, success=False, message="Transaction not found",
                        error="not_found",
                    )
            elif op == "delete":
                txn = crud_transactions.delete_transaction(session, payload["id"])
                if txn is None:
                    return AgentResponse(
                        agent=self.agent_type, success=False, message="Transaction not found",
                        error="not_found",
                    )
            else:
                return AgentResponse(
                    agent=self.agent_type, success=False, message=f"Unknown operation: {op}",
                    error="unknown_operation",
                )

            session.commit()
            return AgentResponse(
                agent=self.agent_type, success=True, message=f"Transaction {op} succeeded",
                data={"id": txn.id, "account_id": txn.account_id, "amount": float(txn.amount), "description": txn.description},
            )
        except KeyError as e:
            return AgentResponse(
                agent=self.agent_type, success=False, message=f"Missing required field: {e}",
                error="missing_field",
            )
        finally:
            session.close()


class ServiceAgent(Agent):
    agent_type = AgentType.SERVICE

    def handle(self, request: AgentRequest) -> AgentResponse:
        import crud_service

        session = SessionLocal()
        payload = request.payload or {}
        try:
            try:
                op = _operation(request.intent)
            except ValueError as e:
                return AgentResponse(
                    agent=self.agent_type, success=False, message=str(e),
                    error="invalid_intent",
                )

            if op == "create":
                req = crud_service.create_service_request(
                    session, payload["account_id"], payload["request_type"], payload.get("details")
                )
            elif op == "read":
                req = crud_service.get_service_request(session, payload["id"])
                if req is None:
                    return AgentResponse(
                        agent=self.agent_type, success=False, message="Service request not found",
                        error="not_found",
                    )
            elif op == "update":
                req = crud_service.update_service_request(
                    session, payload["id"],
                    status=payload.get("status"), details=payload.get("details"),
                )
                if req is None:
                    return AgentResponse(
                        agent=self.agent_type, success=False, message="Service request not found",
                        error="not_found",
                    )
            elif op == "delete":
                req = crud_service.delete_service_request(session, payload["id"])
                if req is None:
                    return AgentResponse(
                        agent=self.agent_type, success=False, message="Service request not found",
                        error="not_found",
                    )
            else:
                return AgentResponse(
                    agent=self.agent_type, success=False, message=f"Unknown operation: {op}",
                    error="unknown_operation",
                )

            session.commit()
            return AgentResponse(
                agent=self.agent_type, success=True, message=f"Service request {op} succeeded",
                data={"id": req.id, "account_id": req.account_id, "request_type": req.request_type, "status": req.status, "details": req.details},
            )
        except KeyError as e:
            return AgentResponse(
                agent=self.agent_type, success=False, message=f"Missing required field: {e}",
                error="missing_field",
            )
        finally:
            session.close()
