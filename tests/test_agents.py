from agents import AccountsAgent, AgentRequest, ServiceAgent, TransactionAgent
from database import SessionLocal
from models import Account, ServiceRequest, Transaction


def _delete(model, id_):
    session = SessionLocal()
    try:
        obj = session.get(model, id_)
        if obj is not None:
            session.delete(obj)
            session.commit()
    finally:
        session.close()


def test_accounts_full_crud_cycle():
    agent = AccountsAgent()

    created = agent.handle(AgentRequest(
        session_id="s1", user_query="open account", intent="accounts.create",
        payload={"owner_name": "Jane", "balance": 100},
    ))
    assert created.success is True
    account_id = created.data["id"]

    try:
        read = agent.handle(AgentRequest(
            session_id="s1", user_query="check", intent="accounts.read",
            payload={"id": account_id},
        ))
        assert read.success is True
        assert read.data["owner_name"] == "Jane"

        updated = agent.handle(AgentRequest(
            session_id="s1", user_query="rename", intent="accounts.update",
            payload={"id": account_id, "owner_name": "Jane Doe"},
        ))
        assert updated.success is True
        assert updated.data["owner_name"] == "Jane Doe"

        deleted = agent.handle(AgentRequest(
            session_id="s1", user_query="close", intent="accounts.delete",
            payload={"id": account_id},
        ))
        assert deleted.success is True

        gone = agent.handle(AgentRequest(
            session_id="s1", user_query="check", intent="accounts.read",
            payload={"id": account_id},
        ))
        assert gone.success is False
        assert gone.error == "not_found"
    finally:
        _delete(Account, account_id)


def test_accounts_missing_field_returns_clean_error():
    agent = AccountsAgent()

    response = agent.handle(AgentRequest(
        session_id="s1", user_query="open account", intent="accounts.create", payload={},
    ))
    assert response.success is False
    assert response.error == "missing_field"


def test_transaction_agent_create_smoke():
    accounts_agent = AccountsAgent()
    txn_agent = TransactionAgent()

    account = accounts_agent.handle(AgentRequest(
        session_id="s1", user_query="open account", intent="accounts.create",
        payload={"owner_name": "Smoke Test", "balance": 0},
    ))
    account_id = account.data["id"]

    try:
        created = txn_agent.handle(AgentRequest(
            session_id="s1", user_query="deposit", intent="transaction.create",
            payload={"account_id": account_id, "amount": 50, "description": "deposit"},
        ))
        assert created.success is True
        assert created.data["amount"] == 50
        _delete(Transaction, created.data["id"])
    finally:
        _delete(Account, account_id)


def test_service_agent_create_smoke():
    accounts_agent = AccountsAgent()
    service_agent = ServiceAgent()

    account = accounts_agent.handle(AgentRequest(
        session_id="s1", user_query="open account", intent="accounts.create",
        payload={"owner_name": "Smoke Test", "balance": 0},
    ))
    account_id = account.data["id"]

    try:
        created = service_agent.handle(AgentRequest(
            session_id="s1", user_query="update address", intent="service.create",
            payload={"account_id": account_id, "request_type": "change_of_address", "details": "123 New St"},
        ))
        assert created.success is True
        assert created.data["status"] == "pending"
        _delete(ServiceRequest, created.data["id"])
    finally:
        _delete(Account, account_id)
