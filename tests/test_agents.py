import pytest

from bank_platform import accounts_server, service_server, transactions_server
from bank_platform.database import SessionLocal
from bank_platform.exceptions import NotFoundError
from bank_platform.models import Account


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
    created = accounts_server.create_account(owner_name="Jane", balance=100)
    account_id = created["id"]

    try:
        read = accounts_server.get_account(account_id)
        assert read["owner_name"] == "Jane"

        updated = accounts_server.update_account(account_id, owner_name="Jane Doe")
        assert updated["owner_name"] == "Jane Doe"

        deleted = accounts_server.delete_account(account_id)
        assert deleted["id"] == account_id

        with pytest.raises(NotFoundError):
            accounts_server.get_account(account_id)
    finally:
        _delete(Account, account_id)


def test_transaction_full_crud_cycle():
    account = accounts_server.create_account(owner_name="Transaction Test", balance=0)
    account_id = account["id"]

    try:
        created = transactions_server.create_transaction(account_id, 50, "deposit")
        assert created["amount"] == 50
        txn_id = created["id"]

        read = transactions_server.get_transaction(txn_id)
        assert read["description"] == "deposit"

        listed = transactions_server.list_transactions(account_id)
        assert any(t["id"] == txn_id for t in listed)

        updated = transactions_server.update_transaction(txn_id, amount=75)
        assert updated["amount"] == 75

        deleted = transactions_server.delete_transaction(txn_id)
        assert deleted["id"] == txn_id

        with pytest.raises(NotFoundError):
            transactions_server.get_transaction(txn_id)
    finally:
        _delete(Account, account_id)


def test_service_full_crud_cycle():
    account = accounts_server.create_account(owner_name="Service Test", balance=0)
    account_id = account["id"]

    try:
        created = service_server.create_service_request(
            account_id, "change_of_address", "123 New St"
        )
        assert created["status"] == "pending"
        request_id = created["id"]

        read = service_server.get_service_request(request_id)
        assert read["request_type"] == "change_of_address"

        updated = service_server.update_service_request(request_id, status="approved")
        assert updated["status"] == "approved"

        deleted = service_server.delete_service_request(request_id)
        assert deleted["id"] == request_id

        with pytest.raises(NotFoundError):
            service_server.get_service_request(request_id)
    finally:
        _delete(Account, account_id)
