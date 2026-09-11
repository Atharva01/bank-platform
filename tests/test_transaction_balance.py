import uuid

from agents import AccountsAgent, AgentRequest, TransactionAgent
from database import SessionLocal
from models import Account

accounts_agent = AccountsAgent()
txn_agent = TransactionAgent()


def _delete_account(account_id):
    session = SessionLocal()
    try:
        obj = session.get(Account, account_id)
        if obj is not None:
            session.delete(obj)
            session.commit()
    finally:
        session.close()


def _open_account(balance):
    created = accounts_agent.handle(AgentRequest(
        session_id="s1", user_query="open account", intent="accounts.create",
        payload={"owner_name": "Balance Test", "balance": balance},
    ))
    assert created.success is True
    return created.data["id"]


def test_credit_transaction_increases_balance():
    account_id = _open_account(100)
    try:
        response = txn_agent.handle(AgentRequest(
            session_id="s1", user_query="deposit", intent="transaction.create",
            payload={"account_id": account_id, "amount": 30, "description": "deposit"},
        ))
        assert response.success is True

        account = accounts_agent.handle(AgentRequest(
            session_id="s1", user_query="check", intent="accounts.read",
            payload={"id": account_id},
        ))
        assert account.data["balance"] == 130
    finally:
        _delete_account(account_id)


def test_debit_transaction_decreases_balance():
    account_id = _open_account(100)
    try:
        response = txn_agent.handle(AgentRequest(
            session_id="s1", user_query="withdraw", intent="transaction.create",
            payload={"account_id": account_id, "amount": -40, "description": "withdrawal"},
        ))
        assert response.success is True

        account = accounts_agent.handle(AgentRequest(
            session_id="s1", user_query="check", intent="accounts.read",
            payload={"id": account_id},
        ))
        assert account.data["balance"] == 60
    finally:
        _delete_account(account_id)


def test_debit_beyond_balance_is_blocked_and_atomic():
    account_id = _open_account(10)
    try:
        response = txn_agent.handle(AgentRequest(
            session_id="s1", user_query="withdraw", intent="transaction.create",
            payload={"account_id": account_id, "amount": -50, "description": "overdraft attempt"},
        ))
        assert response.success is False
        assert response.error == "insufficient_funds"

        account = accounts_agent.handle(AgentRequest(
            session_id="s1", user_query="check", intent="accounts.read",
            payload={"id": account_id},
        ))
        assert account.data["balance"] == 10  # unchanged

        listed = txn_agent.handle(AgentRequest(
            session_id="s1", user_query="statement", intent="transaction.list",
            payload={"account_id": account_id},
        ))
        assert listed.data["transactions"] == []  # no orphaned transaction row
    finally:
        _delete_account(account_id)


def test_transaction_against_nonexistent_account_returns_not_found():
    response = txn_agent.handle(AgentRequest(
        session_id="s1", user_query="deposit", intent="transaction.create",
        payload={"account_id": str(uuid.uuid4()), "amount": 10},
    ))
    assert response.success is False
    assert response.error == "not_found"


def test_zero_amount_transaction_returns_validation_error():
    account_id = _open_account(50)
    try:
        response = txn_agent.handle(AgentRequest(
            session_id="s1", user_query="noop", intent="transaction.create",
            payload={"account_id": account_id, "amount": 0},
        ))
        assert response.success is False
        assert response.error == "validation_error"
    finally:
        _delete_account(account_id)
