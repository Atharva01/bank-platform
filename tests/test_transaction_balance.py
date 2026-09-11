import uuid

import pytest

from bank_platform import accounts_server, transactions_server
from bank_platform.database import SessionLocal
from bank_platform.exceptions import InsufficientFundsError, NotFoundError, ValidationError
from bank_platform.models import Account


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
    return accounts_server.create_account(owner_name="Balance Test", balance=balance)["id"]


def test_credit_transaction_increases_balance():
    account_id = _open_account(100)
    try:
        transactions_server.create_transaction(account_id, 30, "deposit")
        account = accounts_server.get_account(account_id)
        assert account["balance"] == 130
    finally:
        _delete_account(account_id)


def test_debit_transaction_decreases_balance():
    account_id = _open_account(100)
    try:
        transactions_server.create_transaction(account_id, -40, "withdrawal")
        account = accounts_server.get_account(account_id)
        assert account["balance"] == 60
    finally:
        _delete_account(account_id)


def test_debit_beyond_balance_is_blocked_and_atomic():
    account_id = _open_account(10)
    try:
        with pytest.raises(InsufficientFundsError):
            transactions_server.create_transaction(account_id, -50, "overdraft attempt")

        account = accounts_server.get_account(account_id)
        assert account["balance"] == 10  # unchanged

        listed = transactions_server.list_transactions(account_id)
        assert listed == []  # no orphaned transaction row
    finally:
        _delete_account(account_id)


def test_transaction_against_nonexistent_account_returns_not_found():
    with pytest.raises(NotFoundError):
        transactions_server.create_transaction(str(uuid.uuid4()), 10)


def test_zero_amount_transaction_returns_validation_error():
    account_id = _open_account(50)
    try:
        with pytest.raises(ValidationError):
            transactions_server.create_transaction(account_id, 0)
    finally:
        _delete_account(account_id)


def test_editing_transaction_amount_atomically_adjusts_balance():
    account_id = _open_account(100)
    try:
        created = transactions_server.create_transaction(account_id, 30, "deposit")
        assert accounts_server.get_account(account_id)["balance"] == 130

        transactions_server.update_transaction(created["id"], amount=50)
        # delta = 50 - 30 = 20, so 130 + 20 = 150
        assert accounts_server.get_account(account_id)["balance"] == 150
    finally:
        _delete_account(account_id)


def test_editing_transaction_amount_beyond_balance_is_blocked_and_atomic():
    account_id = _open_account(100)
    try:
        created = transactions_server.create_transaction(account_id, 10, "deposit")
        assert accounts_server.get_account(account_id)["balance"] == 110

        # editing to a large debit would take balance negative
        with pytest.raises(InsufficientFundsError):
            transactions_server.update_transaction(created["id"], amount=-500)

        assert accounts_server.get_account(account_id)["balance"] == 110  # unchanged

        unchanged = transactions_server.get_transaction(created["id"])
        assert unchanged["amount"] == 10  # transaction itself untouched
    finally:
        _delete_account(account_id)


def test_deleting_transaction_reverses_its_balance_effect():
    account_id = _open_account(100)
    try:
        created = transactions_server.create_transaction(account_id, 40, "deposit")
        assert accounts_server.get_account(account_id)["balance"] == 140

        transactions_server.delete_transaction(created["id"])
        assert accounts_server.get_account(account_id)["balance"] == 100
    finally:
        _delete_account(account_id)


def test_deleting_transaction_that_would_overdraw_is_blocked():
    account_id = _open_account(100)
    try:
        # a deposit that later funded a withdrawal
        deposit = transactions_server.create_transaction(account_id, 50, "deposit")
        transactions_server.create_transaction(account_id, -120, "withdrawal")
        assert accounts_server.get_account(account_id)["balance"] == 30  # 100 + 50 - 120

        # reversing the deposit would take balance to 30 - 50 = -20
        with pytest.raises(InsufficientFundsError):
            transactions_server.delete_transaction(deposit["id"])

        assert accounts_server.get_account(account_id)["balance"] == 30  # unchanged
    finally:
        _delete_account(account_id)
