import pytest

from bank_platform import accounts_server, service_server
from bank_platform.database import SessionLocal
from bank_platform.exceptions import ValidationError
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


def test_negative_balance_on_create_is_rejected():
    with pytest.raises(ValidationError):
        accounts_server.create_account(owner_name="Bad Balance", balance=-10)


def test_empty_owner_name_on_create_is_rejected():
    with pytest.raises(ValidationError):
        accounts_server.create_account(owner_name="   ", balance=0)


def test_negative_balance_on_update_is_rejected():
    created = accounts_server.create_account(owner_name="Update Test", balance=50)
    account_id = created["id"]
    try:
        with pytest.raises(ValidationError):
            accounts_server.update_account(account_id, balance=-5)
    finally:
        _delete_account(account_id)


def test_empty_owner_name_on_update_is_rejected():
    created = accounts_server.create_account(owner_name="Update Test", balance=50)
    account_id = created["id"]
    try:
        with pytest.raises(ValidationError):
            accounts_server.update_account(account_id, owner_name="")
    finally:
        _delete_account(account_id)


def test_valid_balance_update_still_works():
    created = accounts_server.create_account(owner_name="Update Test", balance=50)
    account_id = created["id"]
    try:
        updated = accounts_server.update_account(account_id, balance=200)
        assert updated["balance"] == 200
    finally:
        _delete_account(account_id)


def test_unknown_request_type_on_service_create_is_rejected():
    created = accounts_server.create_account(owner_name="Service Validation", balance=0)
    account_id = created["id"]
    try:
        with pytest.raises(ValidationError):
            service_server.create_service_request(account_id, "loan_application")
    finally:
        _delete_account(account_id)


def test_known_request_types_are_accepted():
    created = accounts_server.create_account(owner_name="Service Validation", balance=0)
    account_id = created["id"]
    try:
        for request_type in ("change_of_address", "cheque_book_request", "kyc_update"):
            response = service_server.create_service_request(account_id, request_type)
            assert response["request_type"] == request_type
    finally:
        _delete_account(account_id)
