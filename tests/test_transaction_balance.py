import uuid

from bank_platform.agents import AccountsAgent, AgentRequest, TransactionAgent
from bank_platform.database import SessionLocal
from bank_platform.models import Account

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


def _account_balance(account_id):
    response = accounts_agent.handle(AgentRequest(
        session_id="s1", user_query="check", intent="accounts.read",
        payload={"id": account_id},
    ))
    return response.data["balance"]


def test_editing_transaction_amount_atomically_adjusts_balance():
    account_id = _open_account(100)
    try:
        created = txn_agent.handle(AgentRequest(
            session_id="s1", user_query="deposit", intent="transaction.create",
            payload={"account_id": account_id, "amount": 30, "description": "deposit"},
        ))
        assert _account_balance(account_id) == 130

        updated = txn_agent.handle(AgentRequest(
            session_id="s1", user_query="correct", intent="transaction.update",
            payload={"id": created.data["id"], "amount": 50},
        ))
        assert updated.success is True
        # delta = 50 - 30 = 20, so 130 + 20 = 150
        assert _account_balance(account_id) == 150
    finally:
        _delete_account(account_id)


def test_editing_transaction_amount_beyond_balance_is_blocked_and_atomic():
    account_id = _open_account(100)
    try:
        created = txn_agent.handle(AgentRequest(
            session_id="s1", user_query="deposit", intent="transaction.create",
            payload={"account_id": account_id, "amount": 10, "description": "deposit"},
        ))
        assert _account_balance(account_id) == 110

        # editing to a large debit would take balance negative
        updated = txn_agent.handle(AgentRequest(
            session_id="s1", user_query="correct", intent="transaction.update",
            payload={"id": created.data["id"], "amount": -500},
        ))
        assert updated.success is False
        assert updated.error == "insufficient_funds"
        assert _account_balance(account_id) == 110  # unchanged

        unchanged = txn_agent.handle(AgentRequest(
            session_id="s1", user_query="check", intent="transaction.read",
            payload={"id": created.data["id"]},
        ))
        assert unchanged.data["amount"] == 10  # transaction itself untouched
    finally:
        _delete_account(account_id)


def test_deleting_transaction_reverses_its_balance_effect():
    account_id = _open_account(100)
    try:
        created = txn_agent.handle(AgentRequest(
            session_id="s1", user_query="deposit", intent="transaction.create",
            payload={"account_id": account_id, "amount": 40, "description": "deposit"},
        ))
        assert _account_balance(account_id) == 140

        deleted = txn_agent.handle(AgentRequest(
            session_id="s1", user_query="reverse", intent="transaction.delete",
            payload={"id": created.data["id"]},
        ))
        assert deleted.success is True
        assert _account_balance(account_id) == 100
    finally:
        _delete_account(account_id)


def test_deleting_transaction_that_would_overdraw_is_blocked():
    account_id = _open_account(100)
    try:
        # a deposit that later funded a withdrawal
        deposit = txn_agent.handle(AgentRequest(
            session_id="s1", user_query="deposit", intent="transaction.create",
            payload={"account_id": account_id, "amount": 50, "description": "deposit"},
        ))
        txn_agent.handle(AgentRequest(
            session_id="s1", user_query="withdraw", intent="transaction.create",
            payload={"account_id": account_id, "amount": -120, "description": "withdrawal"},
        ))
        assert _account_balance(account_id) == 30  # 100 + 50 - 120

        # reversing the deposit would take balance to 30 - 50 = -20
        response = txn_agent.handle(AgentRequest(
            session_id="s1", user_query="undo deposit", intent="transaction.delete",
            payload={"id": deposit.data["id"]},
        ))
        assert response.success is False
        assert response.error == "insufficient_funds"
        assert _account_balance(account_id) == 30  # unchanged
    finally:
        _delete_account(account_id)
